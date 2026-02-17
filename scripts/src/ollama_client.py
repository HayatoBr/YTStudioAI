# scripts/src/ollama_client.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import urllib.request


def _post_json(url: str, payload: Dict[str, Any], timeout: float = 180.0) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(body)
    except Exception:
        return {"raw": body}


def ollama_chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    host: Optional[str] = None,
    temperature: Optional[float] = None,
    timeout: float = 180.0,
) -> str:
    """
    Simple wrapper for Ollama /api/chat (non-streaming).
    Requires Ollama running locally (default: http://127.0.0.1:11434).
    """
    host = host or os.getenv("AO_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    model = model or os.getenv("AO_OLLAMA_MODEL", "llama3.2:latest")

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    # options
    opts: Dict[str, Any] = {}
    if temperature is None:
        t = os.getenv("AO_OLLAMA_TEMPERATURE", "").strip()
        if t:
            try:
                temperature = float(t)
            except Exception:
                temperature = None
    if temperature is not None:
        opts["temperature"] = float(temperature)
    if opts:
        payload["options"] = opts

    out = _post_json(f"{host}/api/chat", payload, timeout=timeout)

    # Ollama returns {"message":{"role":"assistant","content":"..."}, ...}
    msg = out.get("message") if isinstance(out, dict) else None
    if isinstance(msg, dict):
        return str(msg.get("content") or "").strip()
    if isinstance(out, dict) and "raw" in out:
        return str(out["raw"]).strip()
    return str(out).strip()
