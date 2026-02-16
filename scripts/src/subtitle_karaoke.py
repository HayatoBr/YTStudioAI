# scripts/src/subtitle_karaoke.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Tuple

@dataclass
class KaraokeConfig:
    # número máximo de palavras para tentar destacar (evita filtros enormes)
    max_words: int = 14
    # fração do tempo do chunk reservada para “entrada/saída” do destaque
    pad_frac: float = 0.08

def _word_times(item: Dict[str, Any], cfg: KaraokeConfig) -> List[Tuple[str, float, float]]:
    words = item.get("words") or []
    if not isinstance(words, list):
        words = []
    words = [str(w) for w in words if str(w).strip()]
    words = words[: cfg.max_words]

    st = float(item["start"])
    en = float(item["end"])
    dur = max(0.1, en - st)

    pad = dur * cfg.pad_frac
    usable = max(0.05, dur - 2 * pad)

    n = max(1, len(words))
    per = usable / n

    out = []
    cur = st + pad
    for w in words:
        w_st = cur
        w_en = min(en - pad, cur + per)
        if w_en - w_st < 0.03:
            w_en = min(en - pad, w_st + 0.03)
        out.append((w, float(w_st), float(w_en)))
        cur += per
    return out

def build_karaoke_windows(timeline: List[Dict[str, Any]], cfg: KaraokeConfig | None = None) -> List[Dict[str, Any]]:
    cfg = cfg or KaraokeConfig()
    windows: List[Dict[str, Any]] = []
    for item in timeline:
        wts = _word_times(item, cfg)
        for wi, (w, st, en) in enumerate(wts):
            windows.append({
                "word": w,
                "start": st,
                "end": en,
                "scene_id": item.get("scene_id"),
                "chunk_index": item.get("chunk_index"),
                "word_index": wi,
            })
    return windows
