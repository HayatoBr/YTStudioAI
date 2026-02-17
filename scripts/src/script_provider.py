# scripts/src/script_provider.py
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

from scripts.src.ollama_client import ollama_chat
from scripts.src.rag_wiki import build_case_dossier, dossier_to_prompt

# OpenAI generator stays as the "best quality" backend
from scripts.src.openai_generators import generate_short_script as _openai_short
from scripts.src.openai_generators import generate_long_script as _openai_long


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return default if v is None else str(v)


def _env_bool(name: str, default: str = "0") -> bool:
    return _env(name, default).strip().lower() in ("1", "true", "yes", "y", "on")


def _extract_json_candidate(text: str) -> Optional[str]:
    if not text:
        return None
    s = text.strip()
    if s.startswith("{") and s.endswith("}"):
        return s
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"\s*```$", "", s).strip()
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return s[start : end + 1]
    return None


def _safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    cand = _extract_json_candidate(text)
    if not cand:
        return None
    try:
        obj = json.loads(cand)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _profile() -> str:
    # dev = barato/rápido; publish = qualidade máxima (OpenAI)
    p = _env("AO_PROFILE", "dev").strip().lower()
    return "publish" if p in ("publish", "prod", "production") else "dev"


def _backend() -> str:
    # If publish: force OpenAI (qualidade máxima)
    if _profile() == "publish":
        return "openai"
    # dev defaults to ollama when available, otherwise openai
    b = _env("AO_SCRIPT_BACKEND", "ollama").strip().lower()
    if b in ("ollama", "openai"):
        return b
    return "ollama"


# -------------------------
# Ollama (local) prompts
# -------------------------
def _ollama_short_prompt() -> str:
    return (
        "Você é roteirista investigativo cinematográfico. Canal: Arquivo Oculto.\n"
        "Escreva em PT-BR, tom neutro, documental, ritmo alto.\n"
        "Regras: não use nomes completos de pessoas reais; não acuse indivíduos reais; evite gore.\n"
        "Objetivo: SHORT 45–60s, 130–160 palavras, com 3 evidências concretas (data/horário, local, objeto) "
        "e 1 contradição específica.\n"
        "Saída: retorne APENAS JSON válido com:\n"
        '{ "title": "...", "narration": "...", "scenes": [ {"visual_anchor":"...","camera":"wide|medium|close"} x7 ], "final_question":"..." }\n'
    )


def _ollama_long_prompt(theme: str, minutes: float, scenes_count: int, dossier_block: str) -> str:
    return (
        "Você é roteirista investigativo cinematográfico (Arquivo Oculto). Escreva para TTS, PT-BR.\n"
        "Tom neutro, documental. Sem sensacionalismo. Sem acusar indivíduos reais.\n"
        "Não use nomes completos de pessoas reais: use iniciais.\n\n"
        f"Tema editorial: {theme}\n"
        f"Meta: {minutes:.1f} minutos. Gere exatamente {scenes_count} cenas.\n\n"
        + (dossier_block + "\n\n" if dossier_block else "")
        + "Estrutura obrigatória:\n"
        "1) Abertura fria (20–40s) com detalhe físico + horário/data.\n"
        "2) Contexto (onde/quando/versão oficial).\n"
        "3) Linha do tempo 4–6 blocos (evento + evidência + local).\n"
        "4) Contradição central (versão oficial vs registro conflitante).\n"
        "5) Hipóteses plausíveis (2–3), sem concluir.\n"
        "6) Encerramento curto e marcante.\n\n"
        "Coerência visual: tudo deve ser gerável em imagem documental (arquivo, papel, mapa, prédio, estrada, fita, foto, carimbo).\n\n"
        "Saída: retorne APENAS JSON válido no formato:\n"
        '{ "title":"...", "summary":"...", "narration":"...", "structure":{'
        '"opening_hook":"...","official_version":"...","timeline_blocks":[{"label":"...","description":"...","approx_time_reference":"..."}],'
        '"contradictions":[{"official_claim":"...","conflicting_record":"..."}],"hypotheses":["..."],"closing_statement":"..."'
        '}, "scenes":[{"visual_anchor":"...","location":"...","era":"...","object_focus":"...","camera":"wide|medium|close","mood":"dark|neutral|cold|archival"}],'
        '"thumbnail_prompt":"..." }\n'
    )


def _ollama_generate_json(system: str, user: str) -> Dict[str, Any]:
    raw = ollama_chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    data = _safe_json_loads(raw)
    if isinstance(data, dict):
        return data
    # fallback: pack raw as narration (so pipeline doesn't crash)
    return {"title": "Arquivo Oculto (local)", "narration": raw, "scenes": []}


# -------------------------
# Public API
# -------------------------
def generate_short_script() -> Dict[str, Any]:
    if _backend() == "openai":
        return _openai_short()
    system = "Você responde somente em JSON válido."
    user = _ollama_short_prompt()
    return _ollama_generate_json(system, user)


def generate_long_script(target_minutes: float | None = None) -> Dict[str, Any]:
    if _backend() == "openai":
        return _openai_long(target_minutes=target_minutes)

    # Ollama local + optional Wikipedia dossier (RAG-lite)
    theme = _env("AO_LONG_THEME", "casos_frios")
    minutes = float(target_minutes) if target_minutes is not None else float(_env("AO_LONG_MINUTES", "6.5"))
    minutes = max(1.0, min(20.0, minutes))
    scenes_count = int(round(minutes * 2.15))
    scenes_count = max(8, min(22, scenes_count))

    dossier_block = ""
    if _env_bool("AO_RAG_ENABLED", "1"):
        dossier = build_case_dossier(theme=theme)
        dossier_block = dossier_to_prompt(dossier)

    system = "Você responde somente em JSON válido. Não use markdown."
    user = _ollama_long_prompt(theme=theme, minutes=minutes, scenes_count=scenes_count, dossier_block=dossier_block)
    return _ollama_generate_json(system, user)
