# scripts/src/ffmpeg_tools.py
import os
import shutil
import subprocess
import time
from typing import List, Optional, Dict

def ensure_ffmpeg(ffmpeg_path: Optional[str] = None) -> str:
    if ffmpeg_path and os.path.isfile(ffmpeg_path):
        return ffmpeg_path
    env_path = os.getenv("FFMPEG_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    which = shutil.which("ffmpeg")
    if which:
        return which
    raise RuntimeError(
        "FFmpeg não encontrado. Instale o FFmpeg e/ou adicione ao PATH, "
        "ou defina a variável de ambiente FFMPEG_PATH apontando para ffmpeg.exe."
    )

def ensure_ffprobe() -> str:
    """Tenta achar ffprobe no mesmo local do ffmpeg ou no PATH."""
    ffmpeg = ensure_ffmpeg()
    ffmpeg_dir = os.path.dirname(ffmpeg)
    cand = os.path.join(ffmpeg_dir, "ffprobe.exe" if os.name == "nt" else "ffprobe")
    if os.path.isfile(cand):
        return cand
    which = shutil.which("ffprobe")
    if which:
        return which
    raise RuntimeError("ffprobe não encontrado. Instale FFmpeg completo (com ffprobe) ou adicione ao PATH.")

def get_media_duration_seconds(path: str) -> float:
    """Retorna duração do arquivo (segundos) via ffprobe."""
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"Arquivo não encontrado para medir duração: {path}")
    ffprobe = ensure_ffprobe()
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"ffprobe falhou ao medir duração. STDERR:\n{res.stderr}")
    try:
        return float(res.stdout.strip())
    except Exception as e:
        raise RuntimeError(f"Não foi possível interpretar duração retornada por ffprobe: {res.stdout!r}") from e

def _read_kv_file(path: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
    except Exception:
        return {}
    return data

def run_ffmpeg_with_progress(
    cmd: List[str],
    total_duration_sec: Optional[float] = None,
    label: str = "Renderizando",
    update_interval_sec: float = 0.5,
    check: bool = True,
    no_progress_timeout_sec: float = 30.0,
) -> subprocess.CompletedProcess:
    """
    Executa FFmpeg com progresso via arquivo (-progress <file>).
    Evita deadlock no Windows usando DEVNULL, mas em caso de falha re-executa
    rapidamente o mesmo comando SEM progresso para capturar STDERR útil.
    """
    out_path = cmd[-1] if cmd else None
    out_dir = os.path.dirname(out_path) if out_path else os.getcwd()
    os.makedirs(out_dir, exist_ok=True)

    progress_file = os.path.join(out_dir, f".ffmpeg_progress_{int(time.time())}.txt")
    try:
        if os.path.exists(progress_file):
            os.remove(progress_file)
    except Exception:
        pass

    progress_cmd = cmd[:-1] + ["-loglevel", "error", "-progress", progress_file, "-nostats"] + [cmd[-1]]

    proc = subprocess.Popen(
        progress_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def _fmt_time(seconds: float) -> str:
        seconds = max(0.0, float(seconds))
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    last_print = 0.0
    last_out_time = 0.0
    last_change = time.time()
    last_speed = None

    def _print(out_time_sec: Optional[float], speed: Optional[float]):
        nonlocal last_print
        now = time.time()
        if now - last_print < update_interval_sec:
            return
        last_print = now

        if out_time_sec is None:
            if speed is not None:
                print(f"⏳ {label}… | {speed:.2f}x")
            else:
                print(f"⏳ {label}…")
            return

        if total_duration_sec and total_duration_sec > 0:
            pct = min(100.0, (out_time_sec / total_duration_sec) * 100.0)
            eta_str = ""
            if speed and speed > 0:
                remaining = max(0.0, total_duration_sec - out_time_sec)
                eta = remaining / speed
                eta_str = f" | ETA {_fmt_time(eta)}"
            spd_str = f" | {speed:.2f}x" if speed is not None else ""
            print(f"⏳ {label}: {pct:5.1f}% | {_fmt_time(out_time_sec)} / {_fmt_time(total_duration_sec)}{spd_str}{eta_str}")
        else:
            spd_str = f" | {speed:.2f}x" if speed is not None else ""
            print(f"⏳ {label}: {_fmt_time(out_time_sec)}{spd_str}")

    while True:
        if proc.poll() is not None:
            break

        prog = _read_kv_file(progress_file)
        out_time_sec = None

        if "out_time_ms" in prog:
            try:
                out_time_sec = float(prog["out_time_ms"]) / 1_000_000.0
            except Exception:
                out_time_sec = None
        elif "out_time" in prog:
            try:
                hh, mm, ss = prog["out_time"].split(":")
                out_time_sec = float(hh) * 3600 + float(mm) * 60 + float(ss)
            except Exception:
                out_time_sec = None

        speed = None
        if "speed" in prog:
            try:
                sp = prog["speed"].lower().replace("x", "").strip()
                speed = float(sp) if sp else None
            except Exception:
                speed = None

        if out_time_sec is not None and out_time_sec > last_out_time + 0.01:
            last_out_time = out_time_sec
            last_change = time.time()
        if speed is not None:
            last_speed = speed

        _print(out_time_sec if out_time_sec is not None else last_out_time, last_speed)

        if time.time() - last_change > no_progress_timeout_sec:
            proc.terminate()
            raise RuntimeError(
                f"FFmpeg parece travado (sem avanço de progresso por {no_progress_timeout_sec:.0f}s). "
                "Isso pode indicar problema no comando ou I/O."
            )

        time.sleep(update_interval_sec)

    rc = proc.returncode

    try:
        if os.path.exists(progress_file):
            os.remove(progress_file)
    except Exception:
        pass

    cp = subprocess.CompletedProcess(progress_cmd, rc, stdout="", stderr="")

    if check and rc != 0:
        debug_cmd = cmd[:-1] + ["-loglevel", "error"] + [cmd[-1]]
        dbg = subprocess.run(debug_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        raise RuntimeError(
            "FFmpeg falhou.\n"
            f"CMD:\n{' '.join(debug_cmd)}\n\nSTDERR:\n{dbg.stderr}"
        )

    return cp


import re

_SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")

def detect_speech_segments(
    path: str,
    *,
    silence_db: float = -35.0,
    min_silence_sec: float = 0.25,
    padding_sec: float = 0.05,
) -> List[Dict[str, float]]:
    """Detecta segmentos de fala via silencedetect.

    Retorna lista de dicts: {"start": <sec>, "end": <sec>} representando trechos NÃO-silenciosos.
    Útil para auto-sincronizar legendas sem usar STT.
    """
    if not path or not os.path.isfile(path):
        return []
    ffmpeg = ensure_ffmpeg()
    # silencedetect escreve no STDERR
    cmd = [
        ffmpeg, "-hide_banner", "-nostats",
        "-i", path,
        "-af", f"silencedetect=n={silence_db}dB:d={min_silence_sec}",
        "-f", "null", "-"
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    log = res.stderr or ""

    starts = [float(m.group(1)) for m in _SILENCE_START_RE.finditer(log)]
    ends = [float(m.group(1)) for m in _SILENCE_END_RE.finditer(log)]

    try:
        dur = float(get_media_duration_seconds(path))
    except Exception:
        dur = None

    # Constrói intervalos de silêncio
    silences = []
    for i, stt in enumerate(starts):
        en = ends[i] if i < len(ends) else (dur if dur is not None else stt)
        if en is None:
            continue
        silences.append((max(0.0, stt), max(0.0, en)))

    # Se não detectou nada, assume fala contínua
    if not silences:
        if dur is None:
            return [{"start": 0.0, "end": 9999.0}]
        return [{"start": 0.0, "end": max(0.1, dur)}]

    # Normaliza/ordena e mescla
    silences.sort(key=lambda x: x[0])
    merged = []
    for s,e in silences:
        if not merged or s > merged[-1][1] + 1e-6:
            merged.append([s,e])
        else:
            merged[-1][1] = max(merged[-1][1], e)

    # Fala = complemento dos silêncios
    speech = []
    cur = 0.0
    end_total = dur if dur is not None else merged[-1][1]
    for s,e in merged:
        if s > cur + 1e-6:
            speech.append((cur, s))
        cur = max(cur, e)
    if end_total is not None and end_total > cur + 1e-6:
        speech.append((cur, end_total))

    # Aplica padding (para não colar demais)
    out = []
    for s,e in speech:
        s2 = max(0.0, s - padding_sec)
        e2 = max(s2 + 0.05, e + padding_sec)
        out.append({"start": s2, "end": e2})
    return out

def detect_leading_silence_seconds(path: str, *, silence_db: float = -35.0, min_silence_sec: float = 0.15) -> float:
    """Retorna a duração do silêncio inicial (0 se não detectar)."""
    segs = detect_speech_segments(path, silence_db=silence_db, min_silence_sec=min_silence_sec)
    if not segs:
        return 0.0
    first_start = float(segs[0].get("start", 0.0))
    return max(0.0, first_start)
