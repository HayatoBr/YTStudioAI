# scripts/src/visual_image_pipeline.py
from __future__ import annotations

from typing import Any, Dict

from .image_openai import generate_image_cached

def generate_images_for_scenes(data: Dict[str, Any], video_type: str = "short") -> Dict[str, Any]:
    """Gera (ou reutiliza cache) imagens para cada cena baseada em scene['image_prompt'].
    Escreve scene['_image_path'].
    """
    scenes = data.get("scenes") or []
    if not isinstance(scenes, list) or not scenes:
        return data

    for idx, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        prompt = scene.get("image_prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            continue

        # Short: opcionalmente permitir pular algumas cenas para economizar (deixa para depois).
        img_path, from_cache = generate_image_cached(prompt=prompt, video_type=video_type)
        scene["_image_path"] = img_path
        scene["_image_cached"] = bool(from_cache)

    return data
