from __future__ import annotations

import os
import math
from typing import Dict, Any, List, Optional, Tuple

from .ffmpeg_tools import ensure_ffmpeg, run_ffmpeg_with_progress
from .watermark import validate_watermark
from .subtitle_timing import build_chunk_timeline
from .subtitle_ass import write_karaoke_ass, AssStyle

FFMPEG = ensure_ffmpeg()


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _env_bool(name: str, default: str = "0") -> bool:
    v = os.getenv(name, default)
    if v is None:
        return False
    v = str(v).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _env_float(name: str, default: float = 0.0) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return float(default)


def _ff_escape_ass_path_windows(p: str) -> str:
    """
    Usado em ass='...'
    - backslash -> slash
    - ':' -> '\:' (necessário no Windows)
    - escapa apostrofo
    """
    p2 = p.replace("\\", "/")
    p2 = p2.replace(":", r"\:")
    p2 = p2.replace("'", r"\'")
    return p2


def _first_existing_image(scenes: List[Dict[str, Any]]) -> Optional[str]:
    for s in scenes:
        if isinstance(s, dict):
            p = s.get("_image_path")
            if isinstance(p, str) and p and os.path.exists(p):
                return p
    return None


def _scene_zoom_params(motion: Dict[str, Any]) -> Tuple[float, float]:
    intensity = (motion or {}).get("intensity", "medium")
    direction = (motion or {}).get("direction", "zoom_in")
    if intensity == "low":
        a, b = 1.00, 1.06
    elif intensity == "high":
        a, b = 1.00, 1.14
    else:
        a, b = 1.00, 1.10
    if direction == "zoom_out":
        return b, a
    return a, b


def _build_watermark_chain(input_label: str, wm_input_idx: int) -> Tuple[str, str]:
    """
    Watermark canto inferior esquerdo usando entrada de vídeo/PNG (wm_input_idx).
    Retorna (filter_snippet, out_label)
    """
    out = f"{input_label}_wm"
    # scale2ref para manter proporcional ao vídeo
    snippet = (
        f"[{wm_input_idx}:v]format=rgba[wm_rgba];"
        f"[wm_rgba][{input_label}]scale2ref=w=rw*0.12:h=-1[wm_s][base2];"
        f"[base2][wm_s]overlay=x=W*0.03:y=H-h-H*0.03:format=auto[{out}]"
    )
    return snippet, out


def _build_cinematic_stack(input_label: str) -> Tuple[str, str]:
    """
    Efeitos cinematográficos opcionais (bem leves).
    Controlados por AO_CINEMATIC_ENABLED=1
    """
    if not _env_bool("AO_CINEMATIC_ENABLED", "0"):
        return "", input_label

    out = f"{input_label}_cine"
    vignette = _env_float("AO_CINEMATIC_VIGNETTE", 0.25)
    grain = _env_float("AO_CINEMATIC_GRAIN", 0.0)  # 0 desliga
    parts = [f"[{input_label}]"]
    # leve vinheta
    parts.append(f"vignette=PI/{max(0.01, vignette):.3f}")
    # leve sharpen
    parts.append("unsharp=5:5:0.5:5:5:0.0")
    # granulado opcional
    if grain > 0:
        parts.append(f"noise=alls={grain:.2f}:allf=t")
    parts.append(f"[{out}]")
    return ",".join(parts), out


def _render_video_generic(
    data: Dict[str, Any],
    *,
    duration_sec: float,
    width: int,
    height: int,
    out_dirname: str,
    out_filename: str,
    video_type: str,
    label: str,
) -> str:
    root = _project_root()
    out_dir = os.path.join(root, "output", out_dirname)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_filename)

    audio_path = data.get("_audio_path")
    if not isinstance(audio_path, str) or not audio_path or not os.path.exists(audio_path):
        raise RuntimeError("Áudio não encontrado. Esperado data['_audio_path'] existente.")

    wm_path = validate_watermark(root)
    wm_path = wm_path if isinstance(wm_path, str) and wm_path and os.path.exists(wm_path) else None

    scenes: List[Dict[str, Any]] = data.get("scenes", [])
    scenes = scenes if isinstance(scenes, list) else []


# ASS karaoke
# Auto-sync opcional (sem STT): detecta janelas de fala via silencedetect e distribui chunks só nelas.
if os.getenv("AO_SUB_AUTOSYNC", "0").strip().lower() in {"1", "true", "yes"}:
    try:
        data["_speech_segments"] = detect_speech_segments(audio_path)
    except Exception:
        data.pop("_speech_segments", None)

# Auto-ajuste de offset para compensar silêncio inicial (melhora sync em muitos casos)
if os.getenv("AO_SUB_AUTO_OFFSET", "1").strip().lower() in {"1", "true", "yes"}:
    try:
        lead = float(detect_leading_silence_seconds(audio_path))
        if lead > 0.01:
            base_off = int(os.getenv("AO_SUB_OFFSET_MS", "0") or "0")
            os.environ["AO_SUB_OFFSET_MS"] = str(base_off - int(round(lead * 1000.0)))
    except Exception:
        pass

timeline = build_chunk_timeline(data, float(duration_sec), video_type=video_type)
    subs_dir = os.path.join(root, "output", "subs")
    os.makedirs(subs_dir, exist_ok=True)
    subs_name = f"{video_type}_karaoke.ass" if video_type == "long" else "short_karaoke.ass"
    ass_path = os.path.join(subs_dir, subs_name)
    write_karaoke_ass(timeline, ass_path, style=AssStyle())
    ass_arg = _ff_escape_ass_path_windows(ass_path)

    img_any = _first_existing_image(scenes)

    parallax_enabled = _env_bool("AO_PARALLAX_ENABLED", "0")

    fps = 25

    def build_ken(input_idx: int, out_label: str, dur: float, motion: Dict[str, Any]) -> str:
        frames = max(1, int(dur * fps))
        zoom_start, zoom_end = _scene_zoom_params(motion)
        zoom_expr = f"zoom='{zoom_start}+({zoom_end}-{zoom_start})*on/{frames}'"
        pan_x = "iw/2-(iw/zoom/2)"
        pan_y = "ih/2-(ih/zoom/2)"
        return (
            f"[{input_idx}:v]"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"zoompan={zoom_expr}:x='{pan_x}':y='{pan_y}':d={frames}:s={width}x{height},"
            f"fps={fps},trim=duration={dur:.3f},setpts=PTS-STARTPTS"
            f"[{out_label}]"
        )

    def build_parallax(input_idx: int, out_label: str, dur: float, motion: Dict[str, Any]) -> str:
        frames = max(1, int(dur * fps))
        intensity = (motion or {}).get("intensity", "medium")
        if intensity == "low":
            blur, bg_scale, depth = 6, 1.06, 10
        elif intensity == "high":
            blur, bg_scale, depth = 12, 1.12, 22
        else:
            blur, bg_scale, depth = 10, 1.10, 16

        zoom_start, zoom_end = _scene_zoom_params(motion)
        fg_zoom_expr = f"zoom='{zoom_start}+({zoom_end}-{zoom_start})*on/{frames}'"
        pan_x = "iw/2-(iw/zoom/2)"
        pan_y = "ih/2-(ih/zoom/2)"

        hz = _env_float("AO_PARALLAX_HZ", 0.22)
        # movimento suave do BG (offset no crop)
        bg_x = f"(iw-{width})/2 + {depth}*sin(2*PI*t*{hz})"
        bg_y = f"(ih-{height})/2 + {depth}*cos(2*PI*t*{hz})"

        bgw, bgh = int(width * bg_scale), int(height * bg_scale)

        a = f"s{input_idx}a"
        b = f"s{input_idx}b"
        bg = f"bg{input_idx}"
        fg = f"fg{input_idx}"

        return (
            f"[{input_idx}:v]"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"split=2[{a}][{b}];"
            f"[{a}]scale={bgw}:{bgh}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}:x='{bg_x}':y='{bg_y}',"
            f"boxblur={blur}:1,format=rgba[{bg}];"
            f"[{b}]zoompan={fg_zoom_expr}:x='{pan_x}':y='{pan_y}':d={frames}:s={width}x{height},"
            f"fps={fps},format=rgba[{fg}];"
            f"[{bg}][{fg}]overlay=x=0:y=0:format=auto,trim=duration={dur:.3f},setpts=PTS-STARTPTS"
            f"[{out_label}]"
        )

    # ===== Sem imagens: fundo preto =====
    if not img_any:
        cmd: List[str] = [FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:d={float(duration_sec):.3f}"]
        wm_input_idx = None
        if wm_path:
            cmd += ["-loop", "1", "-t", f"{float(duration_sec):.3f}", "-i", wm_path]
            wm_input_idx = 1
        cmd += ["-i", audio_path]
        audio_input_idx = 1 if wm_input_idx is None else 2

        parts: List[str] = [f"[0:v]format=rgba[vbase]"]
        current = "vbase"

        fx_snip, fx_label = _build_cinematic_stack(current)
        if fx_snip:
            parts.append(fx_snip)
            current = fx_label

        if wm_input_idx is not None:
            wm_snip, wm_out = _build_watermark_chain(current, wm_input_idx)
            parts.append(wm_snip)
            current = wm_out

        parts.append(f"[{current}]ass='{ass_arg}'[v]")
        parts.append("[v]format=yuv420p[vout]")
        filter_complex = ";".join(parts)

        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", f"{audio_input_idx}:a",
            "-shortest",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-movflags", "+faststart",
            "-loglevel", "error",
            out_path,
        ]
        run_ffmpeg_with_progress(cmd, total_duration_sec=float(duration_sec), label=label + " (sem imagens)")
        return out_path

    # ===== Com imagens =====
    n = max(1, len(scenes))
    scene_duration = float(duration_sec) / n

    # entradas: 1 por cena (loop)
    cmd: List[str] = [FFMPEG, "-y"]
    image_paths: List[str] = []

    for scene in scenes:
        img = scene.get("_image_path") if isinstance(scene, dict) else None
        if not isinstance(img, str) or not img or not os.path.exists(img):
            img = img_any
        image_paths.append(img)

    for img in image_paths:
        cmd += ["-loop", "1", "-t", f"{scene_duration:.3f}", "-i", img]

    wm_input_idx = None
    if wm_path:
        cmd += ["-loop", "1", "-t", f"{float(duration_sec):.3f}", "-i", wm_path]
        wm_input_idx = len(image_paths)

    cmd += ["-i", audio_path]
    audio_input_idx = len(image_paths) + (1 if wm_input_idx is not None else 0)

    chain_parts: List[str] = []
    video_nodes: List[str] = []

    for idx, scene in enumerate(scenes):
        motion = scene.get("motion_plan", {}) if isinstance(scene, dict) else {}
        motion_type = (motion or {}).get("type", "ken_burns")
        out_label = f"v{idx}"
        if parallax_enabled and motion_type == "parallax":
            chain_parts.append(build_parallax(idx, out_label, scene_duration, motion))
        else:
            chain_parts.append(build_ken(idx, out_label, scene_duration, motion))
        video_nodes.append(f"[{out_label}]")

    chain_parts.append("".join(video_nodes) + f"concat=n={len(video_nodes)}:v=1:a=0,format=rgba[vbase]")
    current = "vbase"

    fx_snip, fx_label = _build_cinematic_stack(current)
    if fx_snip:
        chain_parts.append(fx_snip)
        current = fx_label

    if wm_input_idx is not None:
        wm_snip, wm_out = _build_watermark_chain(current, wm_input_idx)
        chain_parts.append(wm_snip)
        current = wm_out

    chain_parts.append(f"[{current}]ass='{ass_arg}'[v]")
    chain_parts.append("[v]format=yuv420p[vout]")

    filter_complex = ";".join(chain_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", f"{audio_input_idx}:a",
        "-shortest",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-movflags", "+faststart",
        "-loglevel", "error",
        out_path,
    ]

    run_ffmpeg_with_progress(cmd, total_duration_sec=float(duration_sec), label=label)
    return out_path


# =========================
# Public API
# =========================

def render_short_video(data: Dict[str, Any], duration_sec: float) -> str:
    """SHORT 9:16 (1080x1920)"""
    return _render_video_generic(
        data,
        duration_sec=float(duration_sec),
        width=1080,
        height=1920,
        out_dirname="shorts",
        out_filename="short_auto.mp4",
        video_type="short",
        label="Renderizando SHORT",
    )


def render_long_video_16x9(data: Dict[str, Any], duration_sec: float) -> str:
    """LONG 16:9 (1920x1080)"""
    return _render_video_generic(
        data,
        duration_sec=float(duration_sec),
        width=1920,
        height=1080,
        out_dirname="longs",
        out_filename="long_auto_16x9.mp4",
        video_type="long",
        label="Renderizando LONG 16:9",
    )


def render_long_video_9x16(data: Dict[str, Any], duration_sec: float) -> str:
    """LONG 9:16 (1080x1920)"""
    return _render_video_generic(
        data,
        duration_sec=float(duration_sec),
        width=1080,
        height=1920,
        out_dirname="longs",
        out_filename="long_auto_9x16.mp4",
        video_type="long",
        label="Renderizando LONG 9:16",
    )
