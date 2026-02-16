# scripts/src/image_cache.py
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

def cache_key(prompt: str, model: str, size: str) -> str:
    h = hashlib.sha256()
    h.update((model + "\n" + size + "\n" + prompt).encode("utf-8"))
    return h.hexdigest()[:24]

def cache_path(images_dir: Path, key: str) -> Path:
    return images_dir / f"{key}.png"

def get_cached(images_dir: Path, key: str) -> Optional[Path]:
    p = cache_path(images_dir, key)
    return p if p.exists() else None
