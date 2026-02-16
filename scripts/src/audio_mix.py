# scripts/src/audio_mix.py
from pathlib import Path
from .ffmpeg_tools import ensure_ffmpeg, run_ffmpeg_with_progress

def mix_voice_with_music(
    voice_path: str,
    music_path: str,
    out_path: str,
    duration_sec: int = 55,
    music_volume: float = 0.18,
    label: str = "Mixando áudio",
) -> str:
    """
    Mixagem com melhor qualidade (evita dupla compressão MP3):

    - Decodifica inputs e mixa em filtros (PCM internamente).
    - Saída: AAC (M4A) 256 kbps (mais limpo que MP3).
    - Ducking: sidechaincompress (música abaixa quando voz fala).
    - Fade-in curto para eliminar "click" / artefato no início.
    - Duração exata via atrim/apad.
    """
    ffmpeg = ensure_ffmpeg()

    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # 0:a = voz, 1:a = música
    # - highpass remove grave/ruído de fundo
    # - afade in curto remove artefato de início
    filter_complex = (
        f"[0:a]"
        f"aresample=async=1:first_pts=0,"
        f"highpass=f=80,"
        f"afade=t=in:st=0:d=0.06,"
        f"apad=pad_dur={duration_sec},"
        f"atrim=0:{duration_sec},"
        f"asetpts=N/SR/TB,"
        f"alimiter=limit=0.97"
        f"[voice];"
        f"[1:a]"
        f"atrim=0:{duration_sec},"
        f"asetpts=N/SR/TB,"
        f"volume={music_volume},"
        f"afade=t=in:st=0:d=0.08"
        f"[music];"
        f"[music][voice]"
        f"sidechaincompress=threshold=0.05:ratio=12:attack=20:release=250"
        f"[ducked];"
        f"[voice][ducked]"
        f"amix=inputs=2:duration=longest:dropout_transition=2,"
        f"atrim=0:{duration_sec},"
        f"alimiter=limit=0.97"
        f"[aout]"
    )

    cmd = [
        ffmpeg, "-y",
        "-i", voice_path,
        "-i", music_path,
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-t", str(duration_sec),
        # Saída em AAC para manter qualidade e compatibilidade com MP4 final
        "-c:a", "aac",
        "-b:a", "256k",
        "-movflags", "+faststart",
        str(out_file),
    ]

    run_ffmpeg_with_progress(cmd, total_duration_sec=float(duration_sec), label=label)
    return str(out_file)
