from pathlib import Path
import random
from .subtitles import write_ass, write_srt, build_cues_from_text

def generate_teaser(text: str, duration: int = 20) -> str:
    lines = text.split(".")
    teaser = ". ".join(lines[:2]).strip()
    return teaser[:280]

def generate_curiosity(text: str) -> str:
    prompts = [
        "Pouca gente sabe, mas ",
        "Um detalhe quase esquecido: ",
        "Um fato que quase ninguém conhece: ",
        "O detalhe mais estranho é que ",
    ]
    base = text.split(".")[0].strip()
    return (random.choice(prompts) + base)[:240]

def save_short_assets(base_out: Path, name: str, text: str, duration: int, width: int = 1080, height: int = 1920):
    base_out.mkdir(parents=True, exist_ok=True)
    (base_out / f"{name}.txt").write_text(text, encoding="utf-8")
    cues = build_cues_from_text(text, duration)
    write_srt(cues, base_out / f"{name}.srt")
    write_ass(cues, base_out / f"{name}.ass", width=width, height=height)
