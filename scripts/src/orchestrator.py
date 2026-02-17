from __future__ import annotations


def _pick_music_path(root: str) -> str | None:
    """
    Escolhe uma trilha de fundo se existir em assets/music.
    Prioridade: bg.mp3, depois qualquer arquivo de áudio.
    """
    music_dir = os.path.join(root, "assets", "music")
    if not os.path.isdir(music_dir):
        return None
    preferred = os.path.join(music_dir, "bg.mp3")
    if os.path.exists(preferred):
        return preferred
    for name in os.listdir(music_dir):
        low = name.lower()
        if low.endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg")):
            p = os.path.join(music_dir, name)
            if os.path.isfile(p):
                return p
    return None


def _encode_voice_to_m4a(voice_mp3: str, out_m4a: str, duration_sec: float) -> None:
    """
    Encode simples (sem trilha) para m4a AAC.
    """
    ff = ensure_ffmpeg() if "ensure_ffmpeg" in globals() else None
    ff = ff or os.getenv("FFMPEG_PATH") or "ffmpeg"
    cmd = [
        ff, "-y",
        "-i", voice_mp3,
        "-t", f"{float(duration_sec):.3f}",
        "-c:a", "aac",
        "-b:a", "256k",
        "-movflags", "+faststart",
        "-loglevel", "error",
        out_m4a,
    ]
    run_ffmpeg_with_progress(cmd, total_duration_sec=float(duration_sec), label="Encodando voz (sem trilha)")

import os
import json
from typing import Dict, Any, Union

from scripts.src.script_provider import generate_short_script, generate_long_script
from scripts.src.tts_openai import generate_tts_mp3
from scripts.src.audio_mix import mix_voice_with_music
from scripts.src.renderer import render_short_video, render_long_video_16x9, render_long_video_9x16
from scripts.src.ffmpeg_tools import get_media_duration_seconds
from scripts.src.subtitle_validator import validate_subtitles
from scripts.src.subtitle_from_script import apply_subtitles_from_script

# Compat: visual_extractor teve nomes diferentes ao longo dos patches
import scripts.src.visual_extractor as _ve

def _get_build_visual_plan():
    for name in (
        "build_visual_plan",
        "build_plan",
        "build_visuals",
        "make_visual_plan",
        "create_visual_plan",
        "generate_visual_plan",
        "extract_visual_plan",
        "plan_visuals",
    ):
        fn = getattr(_ve, name, None)
        if callable(fn):
            return fn
    return lambda data: data

_build_visual_plan = _get_build_visual_plan()

def _ensure_dict(data: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Garante que o resultado do gerador seja um dict."""
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        s = data.strip()
        # tenta JSON direto
        if s.startswith("{") and s.endswith("}"):
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
        # tenta extrair bloco JSON dentro do texto
        try:
            start = s.find("{")
            end = s.rfind("}")
            if start != -1 and end != -1 and end > start:
                obj = json.loads(s[start:end+1])
                if isinstance(obj, dict):
                    return obj
        except Exception:
            pass
        # fallback: trata como narração pura
        return {
            "title": "Arquivo Oculto (auto)",
            "narration": s,
            "scenes": [{"scene_id": 1, "subtitle_chunks": ["…"]}],
        }
    # fallback
    return {
        "title": "Arquivo Oculto (auto)",
        "narration": "",
        "scenes": [{"scene_id": 1, "subtitle_chunks": ["…"]}],
    }

def _ensure_scenes(short_data: Dict[str, Any]) -> None:
    scenes = short_data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        short_data["scenes"] = [{"scene_id": 1, "subtitle_chunks": ["…"]}]

def run_auto_short() -> Dict[str, Any]:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    requested_duration_sec = float(os.getenv("AO_SHORT_SECONDS", "55"))
    # Por padrão, usamos a duração REAL do áudio (evita drift de legendas).
    # Se quiser forçar exatamente AO_SHORT_SECONDS, defina AO_FORCE_SHORT_SECONDS=1.
    duration_sec = requested_duration_sec
    print(f"▶ Gerando SHORT ({int(requested_duration_sec)}s) em modo automático...")

    print("🧠 Gerando roteiro automático...")
    short_data_raw = generate_short_script()
    short_data = _ensure_dict(short_data_raw)
    _ensure_scenes(short_data)

    narration_text = str(short_data.get("narration") or "").strip()

    # ✅ Legendas DEVEM vir da narração (não do plano visual)
    scenes = short_data.get("scenes") or []
    if isinstance(scenes, list) and narration_text:
        apply_subtitles_from_script(scenes, narration_text, max_chars=int(os.getenv("AO_SUB_MAX_CHARS", "30")))
        short_data["scenes"] = scenes

    validate_subtitles(short_data, strict=os.getenv("AO_SUBS_STRICT", "0") == "1")

    # Plano visual é para imagens/movimento (não para texto das legendas)
    short_data = _build_visual_plan(short_data)
    try:
        print(f"🧩 Plano visual: {len(short_data.get('scenes', []))} cenas")
    except Exception:
        print("🧩 Plano visual: ok")

    out_audio_dir = os.path.join(root, "output", "audio")
    os.makedirs(out_audio_dir, exist_ok=True)
    voice_path = os.path.join(out_audio_dir, "voice.mp3")
    mixed_path = os.path.join(out_audio_dir, "mixed.m4a")

    print("🎙️ Gerando narração (OpenAI TTS)...")
    generate_tts_mp3(
        narration_text,
        voice_path,
        voice=os.getenv("AO_TTS_VOICE", "cedar"),
        speed=float(os.getenv("AO_TTS_SPEED", "1.0")),
    )

    # Mede duração real da narração para sincronizar legendas/render com o áudio
    try:
        voice_dur = float(get_media_duration_seconds(voice_path))
    except Exception:
        voice_dur = None

    end_pad = float(os.getenv("AO_END_PAD_SEC", "0.25"))
    if voice_dur and voice_dur > 0:
        measured = voice_dur + max(0.0, end_pad)
        if os.getenv("AO_FORCE_SHORT_SECONDS", "0") == "1":
            duration_sec = float(requested_duration_sec)
        else:
            duration_sec = measured
    

    print("🎚️ Mixando voz + trilha (ducking)...")
    mix_voice_with_music(voice_path, mixed_path, duration_sec=duration_sec)

    short_data["_audio_path"] = mixed_path

    print("🎬 Renderizando vídeo SHORT...")
    out_video = render_short_video(short_data, duration_sec=duration_sec)
    print(f"✅ SHORT finalizado!\n📄 Vídeo: {out_video}")
    return {"video": out_video, "audio": mixed_path}


def run_auto_long(minutes: float | None = None) -> Dict[str, Any]:
    """
    Pipeline LONG automático (duração alvo via --minutes):
    - Roteiro LONG (JSON)
    - Legendas extraídas da narração
    - Visual plan (imagens/motion)
    - TTS + mix (ducking)
    - Render 16:9 e 9:16
    """
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    print("▶ Gerando LONG em modo automático...")
    print("🧠 Gerando roteiro LONG automático...")
    long_data = _ensure_dict(generate_long_script(target_minutes=minutes))

    narration_text = str(long_data.get("narration") or "").strip()
    if not narration_text:
        raise RuntimeError("Roteiro LONG veio sem 'narration'.")

    scenes = long_data.get("scenes") or []
    apply_subtitles_from_script(
        scenes,
        narration_text,
        max_chars=int(os.getenv("AO_SUB_MAX_CHARS", "32")),
    )
    long_data["scenes"] = scenes

    validate_subtitles(long_data, strict=os.getenv("AO_SUBS_STRICT", "0") == "1")

    # Visual plan
    if os.getenv("AO_IMAGES_ENABLED", "1") == "1":
        try:
            long_data = _build_visual_plan(long_data)
            try:
                print(f"🧩 Plano visual: {len(long_data.get('scenes', []))} cenas")
            except Exception:
                print("🧩 Plano visual: ok")
        except Exception as e:
            print(f"⚠️ Falha ao gerar imagens (continuando sem imagens): {e}")

    out_audio_dir = os.path.join(root, "output", "audio")
    os.makedirs(out_audio_dir, exist_ok=True)

    voice_path = os.path.join(out_audio_dir, "voice_long.mp3")
    mixed_path = os.path.join(out_audio_dir, "mixed_long.m4a")

    print("🎙️ Gerando narração LONG (OpenAI TTS)...")
    generate_tts_mp3(
        narration_text,
        voice_path,
        voice=os.getenv("AO_TTS_VOICE", "cedar"),
        speed=float(os.getenv("AO_TTS_SPEED", "1.0")),
    )

    # duração real da voz
    try:
        voice_dur = float(get_media_duration_seconds(voice_path))
        end_pad = float(os.getenv("AO_END_PAD_SEC", "0.35"))
        duration_sec = max(1.0, voice_dur + max(0.0, end_pad))
    except Exception:
        duration_sec = float(os.getenv("AO_LONG_FALLBACK_SECONDS", "420"))

    print("🎚️ Mixando voz + trilha (ducking)...")
    music_path = _pick_music_path(root)
    if music_path:
        mix_voice_with_music(
            voice_path=voice_path,
            music_path=music_path,
            out_path=mixed_path,
            duration_sec=duration_sec,
        )
    else:
        print("⚠️ Nenhuma trilha encontrada. Renderizando apenas com a voz.")
        _encode_voice_to_m4a(voice_path, mixed_path, duration_sec)

    # duração final baseada no mix
    try:
        final_dur = float(get_media_duration_seconds(mixed_path))
        if final_dur and final_dur > 0:
            duration_sec = final_dur
    except Exception:
        pass

    long_data["_audio_path"] = mixed_path

    print("🎬 Renderizando vídeo LONG (16:9 e 9:16)...")
    out_16x9 = render_long_video_16x9(long_data, duration_sec=duration_sec)
    out_9x16 = render_long_video_9x16(long_data, duration_sec=duration_sec)

    print("✅ LONG finalizado!")
    print(f"📄 16:9: {out_16x9}")
    print(f"📄 9:16: {out_9x16}")

    return {"video_16x9": out_16x9, "video_9x16": out_9x16, "audio": mixed_path}

