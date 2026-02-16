from __future__ import annotations
from pathlib import Path
import re
from dataclasses import dataclass

from .ffmpeg_tools import media_duration_seconds

@dataclass
class Cue:
    start: float
    end: float
    text: str

def _clean_text(s: str) -> str:
    s = s.replace("\ufeff", "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def _split_sentences(text: str) -> list[str]:
    text = _clean_text(text)
    parts = re.split(r"(?<=[\.!\?…])\s+", text)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if parts else [text]

def _chunk_sentence(sentence: str, max_chars: int = 48) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    chunks = []
    buf = ""
    for token in re.split(r"(,\s+)", sentence):
        if len(buf) + len(token) <= max_chars:
            buf += token
        else:
            if buf.strip():
                chunks.append(buf.strip())
            buf = token
    if buf.strip():
        chunks.append(buf.strip())

    final = []
    for ch in chunks:
        if len(ch) <= max_chars:
            final.append(ch)
            continue
        words = ch.split()
        line = ""
        for w in words:
            if len(line) + len(w) + (1 if line else 0) <= max_chars:
                line = (line + " " + w).strip()
            else:
                final.append(line)
                line = w
        if line:
            final.append(line)
    return final

def build_cues_from_text(text: str, duration_sec: float, min_cue: float = 1.2, max_cue: float = 3.8) -> list[Cue]:
    sentences = _split_sentences(text)
    segments: list[str] = []
    for s in sentences:
        segments.extend(_chunk_sentence(s))

    weights = [max(12, len(seg)) for seg in segments]
    total_w = sum(weights)
    cues: list[Cue] = []
    t = 0.0
    for seg, w in zip(segments, weights):
        seg_dur = duration_sec * (w / total_w) if total_w else 2.0
        seg_dur = max(min_cue, min(max_cue, seg_dur))
        start = t
        end = min(duration_sec, t + seg_dur)
        if end - start < 0.6:
            break
        cues.append(Cue(start=start, end=end, text=seg))
        t = end
        if t >= duration_sec:
            break
    if cues and cues[-1].end < duration_sec:
        cues[-1].end = duration_sec
    return cues


def _chunk_words_for_tiktok(text: str, min_words: int = 2, max_words: int = 5) -> list[str]:
    text = _clean_text(text)
    # remove aspas e sinais excessivos
    text = re.sub(r"[“”"\(\)\[\]]", "", text)
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        take = max_words
        # tenta manter chunks menores perto de pontuação
        window = words[i:i+max_words]
        joined = " ".join(window)
        if re.search(r"[\.!\?…]$", joined) and len(window) >= min_words:
            take = len(window)
        else:
            # se palavra atual é muito longa, reduz
            if len(words[i]) > 10:
                take = min(3, max_words)
        chunk = " ".join(words[i:i+take]).strip()
        if chunk:
            chunks.append(chunk)
        i += take
    return chunks

def _emphasize_one_word(chunk: str) -> str:
    """Aplica estilo TikTok: destaca 1 palavra-chave (negrito) via tags ASS."""
    tokens = chunk.split()
    if not tokens:
        return chunk
    # candidato: palavra mais longa (>=5) que não seja stopword comum
    stop = {"que","de","do","da","dos","das","um","uma","e","a","o","as","os","em","no","na","nos","nas","para","por","com","sem","mas","isso","essa","esse","isso","foi","é","ser","há"}
    cand = None
    for w in sorted(tokens, key=lambda x: len(re.sub(r"\W+","",x)), reverse=True):
        ww = re.sub(r"\W+","",w).lower()
        if len(ww) >= 5 and ww not in stop:
            cand = w
            break
    if not cand:
        cand = tokens[0]
    # injeta tag ASS de negrito apenas no candidato
    out = []
    for t in tokens:
        if t == cand:
            out.append(r"{\b1}" + t + r"{\b0}")
        else:
            out.append(t)
    return " ".join(out)

def build_tiktok_cues_from_text(
    text: str,
    duration_sec: float,
    min_cue: float = 0.9,
    max_cue: float = 2.2,
) -> list[Cue]:
    """Legenda estilo TikTok: chunks curtos (2–5 palavras) com destaque."""
    sentences = _split_sentences(text)
    segments: list[str] = []
    for s in sentences:
        segments.extend(_chunk_words_for_tiktok(s))

    if not segments:
        segments = [_clean_text(text)]

    # duração proporcional ao tamanho (mas limitada)
    weights = [max(8, len(re.sub(r"\W+","",seg))) for seg in segments]
    total_w = sum(weights)
    cues: list[Cue] = []
    t = 0.0
    for seg, w in zip(segments, weights):
        seg_dur = duration_sec * (w / total_w) if total_w else 1.4
        seg_dur = max(min_cue, min(max_cue, seg_dur))
        start = t
        end = min(duration_sec, t + seg_dur)
        if end - start < 0.5:
            break
        cues.append(Cue(start=start, end=end, text=_emphasize_one_word(seg)))
        t = end
        if t >= duration_sec:
            break
    if cues and cues[-1].end < duration_sec:
        cues[-1].end = duration_sec
    return cues

def _fmt_srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    hh = ms // 3600000
    ms -= hh * 3600000
    mm = ms // 60000
    ms -= mm * 60000
    ss = ms // 1000
    ms -= ss * 1000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"

def write_srt(cues: list[Cue], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for i, c in enumerate(cues, 1):
        lines.append(str(i))
        lines.append(f"{_fmt_srt_time(c.start)} --> {_fmt_srt_time(c.end)}")
        txt = c.text
        if len(txt) > 54:
            mid = len(txt)//2
            split = txt.rfind(" ", 0, mid)
            if split == -1:
                split = mid
            txt = txt[:split].strip() + "\n" + txt[split:].strip()
        lines.append(txt)
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")

def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    hh = cs // 360000
    cs -= hh * 360000
    mm = cs // 6000
    cs -= mm * 6000
    ss = cs // 100
    cs -= ss * 100
    return f"{hh}:{mm:02d}:{ss:02d}.{cs:02d}"

def write_ass(cues: list[Cue], out_path: Path, *, width: int, height: int, style: str = 'Default') -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,54,&H00FFFFFF,&H00FFFFFF,&HAA000000,&H00000000,1,0,0,0,100,100,0,0,1,4,1,2,80,80,120,1
Style: TikTok,Arial Black,76,&H00FFFFFF,&H00FFFFFF,&HAA000000,&H00000000,1,0,0,0,100,100,0,0,1,6,2,2,90,90,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for c in cues:
        start = _ass_time(c.start)
        end = _ass_time(c.end)
        txt = c.text.replace("\n", "\\N")
        txt = re.sub(r"\b(não|nunca|sumiu|censurado|arquivo|relatório)\b", lambda m: m.group(0).upper(), txt, flags=re.IGNORECASE)
        events.append(f"Dialogue: 0,{start},{end},{style},,0,0,0,,{txt}")
    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")

def generate_subtitles_from_text_file(
    text_path: Path,
    *,
    audio_path: Path | None = None,
    duration_sec: float | None = None,
) -> tuple[list[Cue], float]:
    text = text_path.read_text(encoding="utf-8")
    if duration_sec is None:
        if audio_path is None:
            raise ValueError("Informe duration_sec ou audio_path para detectar duração.")
        duration_sec = media_duration_seconds(audio_path)
    cues = build_cues_from_text(text, duration_sec)
    return cues, duration_sec
