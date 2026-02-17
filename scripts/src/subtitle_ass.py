from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any
import os
import re


@dataclass
class AssStyle:
    font: str = "Arial"
    fontsize: int = 62
    primary_color: str = "&H00FFFFFF"  # white
    outline_color: str = "&H00000000"  # black
    back_color: str = "&H00000000"
    bold: int = 0
    italic: int = 0
    underline: int = 0
    strikeout: int = 0
    scale_x: int = 100
    scale_y: int = 100
    spacing: int = 0
    angle: int = 0
    border_style: int = 1
    outline: int = 3
    shadow: int = 0
    alignment: int = 2  # bottom-center
    margin_l: int = 60
    margin_r: int = 60
    margin_v: int = 120


def _ass_time(t: float) -> str:
    # h:mm:ss.cs
    t = max(0.0, float(t))
    h = int(t // 3600)
    t -= h * 3600
    m = int(t // 60)
    t -= m * 60
    s = int(t)
    cs = int(round((t - s) * 100))
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass_text(text: str) -> str:
    # basic ASS escaping
    s = str(text)
    s = s.replace("{", r"\{").replace("}", r"\}")
    s = s.replace("\n", r"\N")
    return s


def _karaoke_word_tags(words: List[str], start: float, end: float) -> str:
    # Even distribution across words (synthetic karaoke).
    if not words:
        return _escape_ass_text("")
    total_ms = max(200, int(round((float(end) - float(start)) * 1000)))
    per = max(1, total_ms // max(1, len(words)))
    out = []
    for w in words:
        out.append(r"{\k" + str(max(1, per // 10)) + "}" + _escape_ass_text(w) + " ")
    return "".join(out).strip()


def write_karaoke_ass(timeline: List[Dict[str, Any]] | None, out_path: str, style: AssStyle | None = None) -> str:
    style = style or AssStyle()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # Defensive: if timeline came as None, treat as empty
    timeline = timeline or []

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{style.font},{style.fontsize},{style.primary_color},{style.primary_color},{style.outline_color},{style.back_color},{style.bold},{style.italic},{style.underline},{style.strikeout},{style.scale_x},{style.scale_y},{style.spacing},{style.angle},{style.border_style},{style.outline},{style.shadow},{style.alignment},{style.margin_l},{style.margin_r},{style.margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events: List[str] = []
    for item in timeline:
        try:
            st = float(item.get("start", 0.0))
            en = float(item.get("end", st + 0.5))
            text = str(item.get("text", "")).strip()
            words = item.get("words") or text.split()
        except Exception:
            continue

        if not text:
            continue

        # Karaoke tags (synthetic)
        ktext = _karaoke_word_tags(list(words), st, en)
        line = f"Dialogue: 0,{_ass_time(st)},{_ass_time(en)},Default,,0,0,0,,{ktext}"
        events.append(line)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header + events) + "\n")

    return out_path
