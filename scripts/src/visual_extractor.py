# scripts/src/visual_extractor.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .visual_dna import DNA
from .visual_templates import TEMPLATES, render_template

_TIME_HINTS = [
    ("madrugada", ["madrugada", "2h", "3h", "4h", "antes do amanhecer"]),
    ("noite", ["noite", "23h", "22h", "meia-noite"]),
    ("fim_de_tarde", ["fim da tarde", "anoitecer"]),
]
_DOC_TOKENS = ["arquivo", "registro", "documento", "carimbo", "protocolo", "relatório", "fita", "foto"]

def _lower(s: str) -> str:
    return (s or "").strip().lower()

def _infer_role(scene: Dict[str, Any], idx: int, total: int) -> str:
    role = _lower(scene.get("narrative_role", ""))
    if role:
        return role
    # Inferência simples por posição (Short 7 cenas)
    if idx == 0:
        return "gancho"
    if idx == 1:
        return "contexto"
    if idx in (2, 3, 4):
        return "evidencia"
    if idx == total - 2:
        return "contradicao"
    if idx == total - 1:
        return "desfecho"
    return "contexto"

def _infer_time_of_day(text: str) -> str:
    t = _lower(text)
    for label, keys in _TIME_HINTS:
        if any(k in t for k in keys):
            return label
    return "indefinido"

def _pick_environment(scene: Dict[str, Any], role: str) -> str:
    env = _lower(scene.get("environment", ""))
    if env:
        return env
    anchor = _lower(scene.get("visual_anchor", ""))
    # Heurística por âncora
    if "estrada" in anchor or "rodovia" in anchor or "desapare" in anchor:
        return "estrada vazia à noite"
    if "arquivo" in anchor or "evidenc" in anchor or "document" in anchor:
        return "sala de arquivos"
    if "silhueta" in anchor:
        return "corredor escuro"
    if role == "contexto":
        return "prédio antigo"
    return "sala de arquivos"

def _pick_objects(scene: Dict[str, Any], role: str) -> Tuple[str, str]:
    p = _lower(scene.get("primary_object", ""))
    s = _lower(scene.get("secondary_object", ""))

    anchor = _lower(scene.get("visual_anchor", ""))
    spoken = _lower(scene.get("spoken_excerpt", ""))

    # Se já vierem definidos, respeita
    if p and s:
        return p, s
    if not p:
        # Tenta achar tokens “documentais” no texto
        for tok in _DOC_TOKENS:
            if tok in spoken or tok in anchor:
                if tok == "arquivo" or tok == "registro":
                    p = "documento"
                elif tok == "carimbo":
                    p = "carimbo CONFIDENCIAL"
                elif tok == "fita":
                    p = "fita cassete"
                elif tok == "foto":
                    p = "foto antiga"
                else:
                    p = tok
                break
    if not p:
        # fallback pelo papel narrativo
        if role == "contradicao":
            p = "papel rasgado"
        elif role == "desfecho":
            p = "pasta de arquivo"
        else:
            p = "documento"

    if not s:
        if role == "evidencia":
            s = "carimbo OFICIAL"
        elif role == "contradicao":
            s = "registro sobreposto"
        elif role == "gancho":
            s = "relógio antigo"
        else:
            s = "carimbo CONFIDENCIAL"

    return p, s

def _pick_emotion(role: str) -> str:
    if role in ("gancho", "contradicao"):
        return "inquietante"
    if role == "desfecho":
        return "tenso"
    return "tenso"

def _decide_category(primary_object: str, environment: str) -> str:
    po = _lower(primary_object)
    if any(k in po for k in ["documento", "carimbo", "fita", "foto", "mapa", "papel"]):
        return "object"
    if "sala" in environment or "corredor" in environment or "prédio" in environment or "estrada" in environment:
        return "environment"
    return "symbol"

def _is_concrete(primary_object: str, environment: str) -> bool:
    po = _lower(primary_object)
    env = _lower(environment)
    return (len(po) > 2 and po not in ("algo", "coisa", "mistério")) and (len(env) > 2)

def _ambiguity_risk(scene: Dict[str, Any]) -> str:
    spoken = _lower(scene.get("spoken_excerpt", ""))
    # se tem muitos termos abstratos sem objeto
    abstract = sum(1 for w in ["verdade", "segredo", "silêncio", "mistério", "explicação"] if w in spoken)
    concrete = sum(1 for w in _DOC_TOKENS if w in spoken)
    if abstract >= 2 and concrete == 0:
        return "high"
    if abstract >= 1 and concrete == 0:
        return "medium"
    return "low"

def _fallback_symbol(role: str) -> str:
    # símbolo canônico do DNA
    if role == "contradicao":
        return DNA.concept_to_symbol["contradicao"]
    if role == "gancho":
        return DNA.concept_to_symbol["misterio"]
    if role == "desfecho":
        return DNA.concept_to_symbol["arquivo_oculto"]
    return DNA.concept_to_symbol["evidencia"]

def _choose_motion(role: str, video_type: str, category: str) -> Dict[str, str]:
    # Parallax simples opcional (efeito de profundidade) — aplicado principalmente em Shorts
    parallax_enabled = os.getenv("AO_PARALLAX_ENABLED", "0") == "1"

    # Parâmetros “contrato” (serão usados pelo renderer depois)
    vt = _lower(video_type)
    if vt not in ("short", "long"):
        vt = "short"

    if vt == "short":
        # mais perceptível
        if parallax_enabled and category in ("environment", "object") and role in ("contexto", "evidencia"):
            return {
                "type": "parallax",
                "direction": "subtle",
                "intensity": "medium",
                "focus_target": "primary_object",
            }

        base = {"type": "ken_burns", "direction": "zoom_in", "intensity": "medium", "focus_target": "primary_object"}
        if role == "contexto":
            base["direction"] = "pan_right"
        if role == "desfecho":
            base["direction"] = "zoom_out"
        return base

    # long: sutil
    if parallax_enabled and category in ("environment", "object") and role in ("contexto", "evidencia"):
        return {
            "type": "parallax",
            "direction": "subtle",
            "intensity": "low",
            "focus_target": "primary_object",
        }

    base = {"type": "ken_burns", "direction": "zoom_in", "intensity": "low", "focus_target": "primary_object"}
    if category == "environment":
        base["direction"] = "pan_left"
    if role == "contradicao":
        base["direction"] = "pan_right"
    if role == "desfecho":
        base["direction"] = "zoom_out"
    return base

    # long: sutil
    base = {"type": "ken_burns", "direction": "zoom_in", "intensity": "low", "focus_target": "primary_object"}
    if category == "environment":
        base["direction"] = "pan_left"
    if role == "contradicao":
        base["direction"] = "pan_right"
    if role == "desfecho":
        base["direction"] = "zoom_out"
    return base

def _choose_template(role: str, video_type: str, category: str, ambiguity: str) -> str:
    vt = _lower(video_type)
    if ambiguity == "high":
        return "fallback"
    if role == "evidencia" and category == "object":
        return "close" if vt == "short" else "parallax"
    return "short" if vt == "short" else "long"

def enrich_visual_plan(data: Dict[str, Any], video_type: str = "short") -> Dict[str, Any]:
    """Enriquece data['scenes'] com visual_intent, motion_plan, validation e prompts prontos."""
    scenes = data.get("scenes") or []
    if not isinstance(scenes, list) or not scenes:
        return data

    total = len(scenes)
    enriched: List[Dict[str, Any]] = []

    for idx, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue

        role = _infer_role(scene, idx, total)
        spoken = scene.get("spoken_excerpt") or scene.get("spoken_text") or ""
        # fallback: usar primeiros chars da narração para index
        if not spoken and isinstance(data.get("narration"), str):
            # melhor que nada: não é perfeito, mas evita vazio
            spoken = data["narration"].strip().split("\n")[0][:120]

        environment = _pick_environment(scene, role)
        primary_object, secondary_object = _pick_objects(scene, role)
        emotion = _pick_emotion(role)
        time_of_day = _infer_time_of_day(spoken)
        category = _decide_category(primary_object, environment)
        concrete = _is_concrete(primary_object, environment)
        ambiguity = _ambiguity_risk(scene)

        # Se não é concreto ou risco alto, força fallback de símbolo canônico
        if not concrete or ambiguity == "high":
            sym = _fallback_symbol(role)
            environment = "sala de arquivos"
            primary_object = sym
            secondary_object = "carimbo CONFIDENCIAL"
            category = "symbol"
            concrete = True  # agora é concreto
            ambiguity = "low"

        motion_plan = _choose_motion(role, video_type, category)
        template_key = _choose_template(role, video_type, category, ambiguity)

        params = {
            "environment": environment,
            "primary_object": primary_object,
            "secondary_object": secondary_object,
            "emotion": emotion,
        }
        prompt_map = {
            "short": render_template(TEMPLATES.short, params),
            "long": render_template(TEMPLATES.long, params),
            "fallback": TEMPLATES.fallback,
            "close": render_template(TEMPLATES.close, params),
            "parallax": render_template(TEMPLATES.parallax, params),
        }
        prompt = prompt_map.get(template_key, prompt_map["short" if _lower(video_type) == "short" else "long"])

        scene["narrative_role"] = role
        scene["spoken_excerpt"] = spoken
        scene["visual_intent"] = {
            "category": category,
            "priority": "primary",
            "anchors": {
                "primary_object": primary_object,
                "secondary_object": secondary_object,
                "environment": environment,
                "time_of_day": time_of_day,
                "human_presence": "nenhuma",  # por padrão
                "condition": "antigo",
            },
            "mood": {
                "emotion": emotion,
                "lighting": DNA.lighting,
                "color_palette": DNA.palette,
            },
        }
        scene["motion_plan"] = motion_plan
        scene["validation"] = {
            "is_concrete": True,
            "ambiguity_risk": ambiguity,
            "fallback_allowed": True,
            "template": template_key,
        }
        scene["image_prompt"] = prompt

        enriched.append(scene)

    data["scenes"] = enriched
    return data

def visual_plan_summary(data: Dict[str, Any]) -> str:
    scenes = data.get("scenes") or []
    if not isinstance(scenes, list) or not scenes:
        return "ℹ️ Plano visual: 0 cenas."
    counts: Dict[str, int] = {}
    fallbacks = 0
    for s in scenes:
        if not isinstance(s, dict):
            continue
        tmpl = ((s.get("validation") or {}).get("template")) or "unknown"
        counts[tmpl] = counts.get(tmpl, 0) + 1
        if tmpl == "fallback":
            fallbacks += 1
    top = ", ".join([f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))])
    return f"🧩 Plano visual: {len(scenes)} cenas | {top} | fallbacks={fallbacks}"
