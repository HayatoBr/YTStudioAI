# scripts/src/image_openai.py
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from openai import OpenAI

from .image_budget import load_budget_config, can_spend, record_spend
from .image_cache import cache_key, get_cached, cache_path

def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]

def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def _save_png_from_b64(b64_data: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(b64_data))

def _extract_b64_from_response(resp: Any) -> Optional[str]:
    # Compatibilidade com diferentes formatos do SDK/endpoint
    try:
        data = getattr(resp, "data", None)
        if data and isinstance(data, list) and data:
            item = data[0]
            # item pode ser dict-like ou objeto
            if isinstance(item, dict):
                return item.get("b64_json") or item.get("b64")
            return getattr(item, "b64_json", None) or getattr(item, "b64", None)
    except Exception:
        pass
    return None

def generate_image_cached(
    prompt: str,
    video_type: str = "short",
    model: Optional[str] = None,
    size: Optional[str] = None,
    force: bool = False,
) -> Tuple[str, bool]:
    """
    Gera imagem via OpenAI com cache + budget guard.
    Retorna (path_png, from_cache).
    """
    root = _project_root()
    images_dir = root / "output" / "images"
    _ensure_dir(images_dir)

    # Defaults por tipo
    if model is None:
        model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
    if size is None:
        # Shorts: 1024; Longs: 1024 (por enquanto). Pode subir para 1536/2048 depois com orçamento.
        size = os.getenv("AO_IMAGE_SIZE", "1024x1024")

    key = cache_key(prompt=prompt, model=model, size=size)
    cached = get_cached(images_dir, key)
    if cached and not force:
        return str(cached), True

    cfg = load_budget_config(root)
    estimate = float(os.getenv("AO_COST_PER_IMAGE_USD", str(cfg.cost_per_image_usd)))
    ok, remaining = can_spend(cfg, estimate)
    if not ok:
        raise RuntimeError(
            f"Budget guard: limite mensal atingido. Tentou gastar ~${estimate:.2f}, "
            f"restante ~${remaining:.2f}. Ajuste AO_BUDGET_USD/AO_COST_PER_IMAGE_USD ou aguarde o próximo mês."
        )

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Tentamos pedir b64 para salvar local e manter pipeline offline.
    resp = None

    # Alguns endpoints/contas rejeitam 'response_format' com erro 400 ("Unknown parameter").
    # Tentamos com b64_json e, se falhar por esse motivo, refazemos sem o parâmetro.
    try:
        resp = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            response_format="b64_json",
        )
    except Exception as e:
        msg = str(e)
        if "response_format" in msg and ("Unknown parameter" in msg or "unknown_parameter" in msg):
            resp = client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
            )
        else:
            raise

    b64_img = _extract_b64_from_response(resp)
    if not b64_img:
        # Fallback: alguns formatos retornam URL. Baixa e salva localmente.
        try:
            data = getattr(resp, "data", None)
            if data and isinstance(data, list) and data:
                item = data[0]
                url = item.get("url") if isinstance(item, dict) else getattr(item, "url", None)
                if url:
                    import requests  # type: ignore

                    r = requests.get(url, timeout=60)
                    r.raise_for_status()
                    out_path = cache_path(images_dir, key)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(r.content)

                    record_spend(
                        cfg,
                        amount_usd=estimate,
                        kind="image",
                        meta={"model": model, "size": size, "cache_key": key, "via": "url"},
                    )
                    return str(out_path), False
        except Exception:
            pass

    if not b64_img:
        raise RuntimeError("OpenAI não retornou b64_json para a imagem. Verifique modelo/SDK.")

    out_path = cache_path(images_dir, key)
    _save_png_from_b64(b64_img, out_path)

    record_spend(
        cfg,
        amount_usd=estimate,
        kind="image",
        meta={"model": model, "size": size, "cache_key": key},
    )

    return str(out_path), False
