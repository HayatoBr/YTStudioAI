# scripts/src/watermark.py
from __future__ import annotations

import os
from typing import Optional

def find_watermark(project_root: str) -> Optional[str]:
    # Procura em locais comuns dentro do projeto
    candidates = [
        os.path.join(project_root, "assets", "watermark.png"),
        os.path.join(project_root, "assets", "watermark.webp"),
        os.path.join(project_root, "assets", "branding", "watermark.png"),
        os.path.join(project_root, "assets", "branding", "watermark.webp"),
        os.path.join(project_root, "assets", "logo.png"),
        os.path.join(project_root, "assets", "logo.webp"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return os.path.abspath(p)
    return None

def validate_watermark(project_root: str) -> Optional[str]:
    # Compat: retorna path ou None (não quebra render)
    return find_watermark(project_root)
