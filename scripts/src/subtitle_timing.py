# scripts/src/subtitle_timing.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import os


@dataclass
class TimingConfig:
    # Shorts
    short_min_chunk: float = 0.7
    short_max_chunk: float = 1.2
    # Longs
    long_min_chunk: float = 1.5
    long_max_chunk: float = 3.0

    # Enter slightly earlier to feel "snappier".
    anticipation_ms: int = 100

    # Global shift (positive delays subtitles, negative anticipates)
    offset_ms: int = 0

    # Prevent huge empty gaps when some scenes have no subtitle_chunks.
    max_gap_ms: int = 180


def _clamp(v: float, a: float, b: float) -> float:
    return max(a, min(b, v))


def _split_words(text: str) -> List[str]:
    return [w for w in str(text).strip().split() if w]


def _get_int_env(name: str, default: int) -> int:
    try:
        v = os.getenv(name)
        return default if v is None or str(v).strip() == "" else int(str(v).strip())
    except Exception:
        return default


def _get_float_env(name: str, default: float) -> float:
    try:
        v = os.getenv(name)
        return default if v is None or str(v).strip() == "" else float(str(v).strip())
    except Exception:
        return default


def _collect_chunks(data: Dict[str, Any]) -> List[Tuple[int, str]]:
    """Collect subtitle chunks in a robust way.

    Priority:
    1) data['subtitle_chunks']  (global)
    2) data['narration_chunks'] (global)
    3) flatten data['scenes'][*]['subtitle_chunks']

    Returns list of (scene_id, text) to preserve some scene metadata when available.
    """
    # 1) Global chunks
    for key in ("subtitle_chunks", "narration_chunks"):
        chunks = data.get(key)
        if isinstance(chunks, list) and chunks:
            return [(1, str(c)) for c in chunks if str(c).strip()]

    # 2) Scene chunks
    scenes = data.get("scenes") or []
    out: List[Tuple[int, str]] = []
    if isinstance(scenes, list):
        for si, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                continue
            scene_id = int(scene.get("scene_id", si + 1))
            chunks = scene.get("subtitle_chunks")
            if not isinstance(chunks, list) or not chunks:
                continue
            for c in chunks:
                t = str(c).strip()
                if t:
                    out.append((scene_id, t))
    return out


def _get_speech_windows(data: Dict[str, Any], duration_sec: float) -> List[Tuple[float, float]]:
    """Optional speech windows for autosync.

    If AO_SUB_AUTOSYNC=1 and data contains _speech_segments (list of {start,end}),
    we will distribute subtitle chunks across those windows instead of the full duration.
    """
    enabled = os.getenv("AO_SUB_AUTOSYNC", "0").strip().lower() in {"1", "true", "yes"}
    if not enabled:
        return [(0.0, max(0.1, float(duration_sec)))]

    segs = data.get("_speech_segments")
    if not isinstance(segs, list) or not segs:
        return [(0.0, max(0.1, float(duration_sec)))]

    out: List[Tuple[float, float]] = []
    for it in segs:
        if not isinstance(it, dict):
            continue
        try:
            s = float(it.get("start", 0.0))
            e = float(it.get("end", 0.0))
        except Exception:
            continue
        if e - s >= 0.10:
            out.append((max(0.0, s), max(0.0, e)))
    if not out:
        return [(0.0, max(0.1, float(duration_sec)))]
    # clamp to duration
    dur = max(0.1, float(duration_sec))
    out2 = []
    for s,e in out:
        if s >= dur:
            continue
        out2.append((s, min(dur, e)))
    return out2 or [(0.0, dur)]



def build_chunk_timeline(
    data: Dict[str, Any],
    duration_sec: float,
    video_type: str = "short",
    cfg: Optional[TimingConfig] = None,
) -> List[Dict[str, Any]]:
    """Build a robust subtitle timeline.

    Key guarantees:
    - Never relies on "scene slots" that can create long gaps.
    - Timeline is continuous (gaps capped), covering the full usable window.
    - Supports min/max duration per chunk and re-balances to match total duration.
    """

    cfg = cfg or TimingConfig()

    # ENV overrides
    cfg.anticipation_ms = _get_int_env("AO_SUB_ANTICIPATION_MS", cfg.anticipation_ms)
    cfg.offset_ms = _get_int_env("AO_SUB_OFFSET_MS", cfg.offset_ms)
    cfg.max_gap_ms = _get_int_env("AO_SUB_MAX_GAP_MS", cfg.max_gap_ms)

    cfg.short_min_chunk = _get_float_env("AO_SUB_SHORT_MIN", cfg.short_min_chunk)
    cfg.short_max_chunk = _get_float_env("AO_SUB_SHORT_MAX", cfg.short_max_chunk)
    cfg.long_min_chunk = _get_float_env("AO_SUB_LONG_MIN", cfg.long_min_chunk)
    cfg.long_max_chunk = _get_float_env("AO_SUB_LONG_MAX", cfg.long_max_chunk)

    if video_type.lower() == "long":
        min_d, max_d = cfg.long_min_chunk, cfg.long_max_chunk
    else:
        min_d, max_d = cfg.short_min_chunk, cfg.short_max_chunk

    items = _collect_chunks(data)
    if not items:
        return []

    # Use most of the duration (tiny safety margin to avoid edge clipping in render)
    total = max(0.1, float(duration_sec))
    windows = _get_speech_windows(data, total)
    window_total = sum(max(0.0, e - s) for s, e in windows) or total
    usable = max(0.1, window_total * 0.98)

    # Weights by text length (proxy for speech time)
    weights = [max(1, len(t)) for _, t in items]
    total_w = float(sum(weights)) if weights else 1.0

    # Initial durations by weights
    durations = [usable * (w / total_w) for w in weights]

    # Clamp
    durations = [_clamp(d, min_d, max_d) for d in durations]

    # Re-balance to match usable exactly (avoid ending early and avoid long gaps)
    def rebalance_to_total(ds: List[float], target: float) -> List[float]:
        ds = list(ds)
        cur = float(sum(ds))
        if cur <= 0:
            return ds

        # If too long: scale down but keep floor at 0.20s
        if cur > target:
            scale = target / cur
            ds = [max(0.20, d * scale) for d in ds]
            cur = float(sum(ds))

        # If too short: distribute leftover across chunks (prefer those below max_d)
        if cur < target:
            remaining = target - cur
            # simple iterative distribution
            for _ in range(6):
                if remaining <= 1e-6:
                    break
                headroom = [max(0.0, max_d - d) for d in ds]
                hr_sum = float(sum(headroom))
                if hr_sum <= 1e-6:
                    # no headroom: add evenly
                    add = remaining / len(ds)
                    ds = [d + add for d in ds]
                    remaining = 0.0
                    break
                # proportional add by headroom
                adds = [remaining * (hr / hr_sum) for hr in headroom]
                ds2 = []
                for d, a in zip(ds, adds):
                    nd = min(max_d, d + a)
                    ds2.append(nd)
                ds = ds2
                cur2 = float(sum(ds))
                remaining = max(0.0, target - cur2)

        # Final tiny correction
        cur = float(sum(ds))
        if abs(cur - target) > 1e-4 and cur > 0:
            scale = target / cur
            ds = [max(0.20, d * scale) for d in ds]
        return ds

    durations = rebalance_to_total(durations, usable)

    ant = cfg.anticipation_ms / 1000.0
    off = cfg.offset_ms / 1000.0
    max_gap = cfg.max_gap_ms / 1000.0

    timeline: List[Dict[str, Any]] = []
    t = 0.0


def _map_local_to_global(local_t: float) -> float:
    """Maps a local timeline position (0..usable) into real time across speech windows."""
    remaining = float(local_t)
    for s, e in windows:
        wlen = max(0.0, e - s)
        if wlen <= 0:
            continue
        if remaining <= wlen + 1e-9:
            return float(s + remaining)
        remaining -= wlen
    # fallback end
    return float(windows[-1][1])


    for idx, ((scene_id, text), dur) in enumerate(zip(items, durations)):
        # Keep continuity: no big gaps between chunks
        if timeline:
            prev_end = float(timeline[-1]["end_raw"])
            if t - prev_end > max_gap:
                t = prev_end + max_gap

        st_raw_local = t
        en_raw_local = min(usable, t + float(dur))
        st_raw = _map_local_to_global(st_raw_local)
        en_raw = _map_local_to_global(en_raw_local)

        # Apply anticipation/offset to displayed times
        st = max(0.0, (st_raw - ant) + off)
        en = max(st + 0.20, en_raw + off)

        # Bound to usable+offset
        max_end = usable + max(0.0, off) + 0.05
        if en > max_end:
            en = max_end

        timeline.append(
            {
                "text": text,
                "words": _split_words(text),
                "start": float(st),
                "end": float(en),
                # raw for internal continuity checks
                "start_raw": float(st_raw),
                "end_raw": float(en_raw),
                "scene_id": int(scene_id),
                "chunk_index": int(idx),
            }
        )

        t = en_raw_local

    # Remove helper fields (keep output stable)
    for it in timeline:
        it.pop("start_raw", None)
        it.pop("end_raw", None)

    return timeline
