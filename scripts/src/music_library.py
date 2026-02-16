# scripts/src/music_library.py
import os
import random
from typing import List, Dict, Optional

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".ogg")

def scan_music_library(music_dir: str) -> List[str]:
    """Scan a directory recursively and return a list of audio file paths."""
    if not music_dir or not os.path.isdir(music_dir):
        return []
    tracks: List[str] = []
    for root, _, files in os.walk(music_dir):
        for fn in files:
            if fn.lower().endswith(AUDIO_EXTS):
                tracks.append(os.path.join(root, fn))
    tracks.sort()
    return tracks

def choose_track(tracks: List[str], mood: str = "misterio", seed: Optional[int] = None) -> Optional[str]:
    """Choose a track deterministically if seed provided; otherwise random."""
    if not tracks:
        return None
    rng = random.Random(seed) if seed is not None else random

    # If you later want mood tagging, you can implement filename keywords here.
    # For now: simple deterministic shuffle based on mood.
    mood_key = (mood or "misterio").lower()
    indexed = list(enumerate(tracks))
    rng.shuffle(indexed)
    # Choose first after shuffle; stable across runs if seed is stable.
    return indexed[0][1]
