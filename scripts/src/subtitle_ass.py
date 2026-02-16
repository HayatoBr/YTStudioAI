from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any
import os
import re


@dataclass
class AssStyle:
    font: str = "Arial"
    fontsize: int = 62
    outline: int = 6
    shadow: int = 2
    margin_v: int = 180
    primary: str = "&H00FFFFFF"       # branco
    secondary: str = "&H0000FFFF"     # amarelo (BGR)
    outlinec: str = "&H00000000"      # preto
    back: str = "&H64000000"          # preto translúcido


def _ass_time(t: float) -> str:
    # H:MM:SS.CS (centiseconds)
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{").replace("}", "\\}")
    text = text.replace("\n", " ").replace("\r", " ")
    return text


_word_re = re.compile(r"\S+")


def _karaoke_tags(text: str, start: float, end: float, max_words: int = 16) -> str:
    words = _word_re.findall(text)
    if not words:
        return _escape_ass(text)

    words = words[:max_words]
    dur_cs = max(10, int(round((end - start) * 100)))  # mínimo 0.10s
    per = max(1, dur_cs // len(words))

    out = []
    for w in words:
        out.append("{\\k%d}%s " % (per, _escape_ass(w)))
    return "".join(out).strip()


def write_karaoke_ass(timeline: List[Dict[str, Any]], out_path: str, style: AssStyle | None = None) -> str:
    style = style or AssStyle()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: TikTok,{style.font},{style.fontsize},{style.primary},{style.secondary},{style.outlinec},{style.back},0,0,0,0,"
        f"100,100,0,0,1,{style.outline},{style.shadow},2,80,80,{style.margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events = []
    for item in timeline:
        st = float(item["start"])
        en = float(item["end"])
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        kara = _karaoke_tags(text, st, en)
        events.append(f"Dialogue: 0,{_ass_time(st)},{_ass_time(en)},TikTok,,0,0,0,,{kara}")

    content = "\n".join(header + events) + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return out_path
