# scripts/src/subtitle_drawtext.py
from __future__ import annotations

import os
from typing import List, Dict, Any, Optional

def ff_escape_text(text: str) -> str:
    t = text.replace('\\', r'\\\\')
    t = t.replace(':', r'\\:')
    t = t.replace("'", r"\\'")
    t = t.replace('%', r'\\%')
    return t

def ff_escape_path(p: str) -> str:
    return p.replace("'", r"\'")

def ff_escape_path_drawtext(p: str) -> str:
    p2 = p.replace('\\', '/')
    p2 = p2.replace(':', r'\:')
    p2 = p2.replace("'", r"\'")
    return p2

def _font_opt() -> str:
    fontfile = os.getenv("AO_FONT_FILE", "").strip()
    fontname = os.getenv("AO_FONT_NAME", "Arial").strip()
    if fontfile:
        return f"fontfile='{ff_escape_path_drawtext(fontfile)}'"
    return f"font='{fontname}'"

def build_drawtext_chain(
    timeline: List[Dict[str, Any]],
    input_label: str,
    output_label: str,
    avoid_bottom_margin_px: int = 130,
) -> str:
    if not timeline:
        return f"{input_label}null{output_label}"

    y_expr = f"h-{avoid_bottom_margin_px}-text_h"
    x_expr = "(w-text_w)/2"
    fontsize_expr = "h*0.055"

    common = [
        f"x={x_expr}",
        f"y={y_expr}",
        f"fontsize={fontsize_expr}",
        "fontcolor=white",
        "borderw=6",
        "bordercolor=black@0.85",
        "shadowx=2",
        "shadowy=2",
        _font_opt(),
    ]

    parts = []
    current = input_label
    for i, item in enumerate(timeline):
        text = ff_escape_text(str(item["text"]))
        st = float(item["start"])
        en = float(item["end"])
        nxt = f"[sub{i}]"
        enable = f"enable='between(t,{st:.3f},{en:.3f})'"
        draw = "drawtext=" + ":".join([f"text='{text}'", enable] + common)
        parts.append(f"{current}{draw}{nxt}")
        current = nxt

    parts[-1] = parts[-1].replace(current, output_label)
    return ";".join(parts)

def build_karaoke_highlight_chain(
    windows: List[Dict[str, Any]],
    input_label: str,
    output_label: str,
    avoid_bottom_margin_px: int = 130,
) -> str:
    """Overlay de palavra destacada (1 palavra por vez) no mesmo lugar da legenda."""
    if not windows:
        return f"{input_label}null{output_label}"

    y_expr = f"h-{avoid_bottom_margin_px}-text_h"
    x_expr = "(w-text_w)/2"
    fontsize_expr = "h*0.060"  # um pouco maior para destaque

    common = [
        f"x={x_expr}",
        f"y={y_expr}",
        f"fontsize={fontsize_expr}",
        "fontcolor=yellow",
        "borderw=8",
        "bordercolor=black@0.9",
        "shadowx=2",
        "shadowy=2",
        _font_opt(),
    ]

    parts = []
    current = input_label
    for i, w in enumerate(windows[:400]):  # hard cap para não explodir filtros
        word = ff_escape_text(str(w["word"]))
        st = float(w["start"])
        en = float(w["end"])
        nxt = f"[kw{i}]"
        enable = f"enable='between(t,{st:.3f},{en:.3f})'"
        draw = "drawtext=" + ":".join([f"text='{word}'", enable] + common)
        parts.append(f"{current}{draw}{nxt}")
        current = nxt

    parts[-1] = parts[-1].replace(current, output_label)
    return ";".join(parts)
