from __future__ import annotations

import os
import re
import math
from typing import List, Dict, Any

# Split on sentence end or newlines
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

# Tokens that may appear in the script but should never be spoken nor subtitled
# (The TTS layer already strips some of these; we also strip for subtitles.)
_STRIP_TOKENS = [
    r"\[PAUSA_FINAL\]",
    r"\[PAUSA\]",
    r"\[SILENCIO\]",
    r"\[SILÊNCIO\]",
]

def _strip_control_tokens(text: str) -> str:
    t = text or ""
    for pat in _STRIP_TOKENS:
        t = re.sub(pat, " ", t, flags=re.IGNORECASE)
    return t

def _clean(s: str) -> str:
    s = _strip_control_tokens((s or "").strip())
    # normalize whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s

def split_into_chunks(text: str, max_chars: int = 32) -> List[str]:
    """Divide a narração em frases curtas estilo TikTok (sem STT).

    Observação:
    - Remove tokens de controle como [PAUSA_FINAL] para não aparecerem nas legendas.
    """
    text = _clean(text)
    if not text:
        return []

    parts = [p.strip() for p in _SENT_SPLIT.split(text) if p.strip()]
    out: List[str] = []

    for p in parts:
        p = _clean(p)
        if not p:
            continue

        if len(p) <= max_chars:
            out.append(p)
            continue

        # quebra por vírgula / ponto e vírgula / travessão
        sub = [x.strip() for x in re.split(r"[;,–—]+\s*", p) if x.strip()]
        for s in sub:
            s = _clean(s)
            if not s:
                continue

            if len(s) <= max_chars:
                out.append(s)
            else:
                # fallback: quebra por palavras
                words = s.split()
                cur = ""
                for w in words:
                    if not cur:
                        cur = w
                    elif len(cur) + 1 + len(w) <= max_chars:
                        cur += " " + w
                    else:
                        if cur:
                            out.append(cur)
                        cur = w
                if cur:
                    out.append(cur)

    return out

def apply_subtitles_from_script(
    scenes: List[Dict[str, Any]],
    narration_text: str,
    max_chars: int = 32,
) -> List[Dict[str, Any]]:
    """Substitui scene['subtitle_chunks'] por chunks extraídos da narração.

    Mudança importante:
    - NÃO insere placeholders (ex.: "…") em cenas sem fala.
      Isso evita legendas fantasmas como "PAUSA FINAL" e "…" no fim.
    - Se quiser placeholders, habilite AO_SUB_FILLER=1.
    """
    if not scenes or not isinstance(scenes, list):
        return scenes

    filler_enabled = (os.getenv("AO_SUB_FILLER", "0").strip() in {"1", "true", "True"})

    chunks = split_into_chunks(narration_text, max_chars=max_chars)

    n = max(1, len(scenes))
    per = max(1, math.ceil(len(chunks) / n)) if chunks else 0

    idx = 0
    for sc in scenes:
        if not isinstance(sc, dict):
            continue

        take: List[str] = []
        if per > 0 and idx < len(chunks):
            take = chunks[idx : idx + per]
            idx += per

        # If no text allocated to this scene, either leave empty or (optionally) add a subtle filler.
        if not take:
            sc["subtitle_chunks"] = (["…"] if filler_enabled else [])
        else:
            sc["subtitle_chunks"] = take

    return scenes
