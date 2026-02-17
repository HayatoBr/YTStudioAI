# scripts/src/openai_generators.py
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from openai import OpenAI

# OpenAI client reads OPENAI_API_KEY from environment by default
_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# -------------------------
# JSON helpers
# -------------------------
def _extract_json_candidate(text: str) -> Optional[str]:
    if not text:
        return None
    s = text.strip()

    # Pure JSON fast path
    if s.startswith("{") and s.endswith("}"):
        return s

    # Strip fenced blocks
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"\s*```$", "", s).strip()

    # Outermost braces
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


def _repair_to_json(model: str, bad_output: str, schema: str) -> str:
    prompt = (
        "Converta o conteúdo abaixo em APENAS um JSON válido (sem markdown, sem texto extra), "
        "seguindo rigorosamente o schema fornecido.\n\n"
        f"SCHEMA:\n{schema}\n\n"
        f"CONTEÚDO:\n{bad_output}"
    )
    resp = _client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Você é um reparador de JSON. Retorne somente JSON válido."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
    )
    return (resp.choices[0].message.content or "").strip()


# -------------------------
# SHORT (45–60s)
# -------------------------
def _default_short_scenes() -> List[Dict[str, Any]]:
    anchors = [
        "arquivo confidencial com carimbo",
        "corredor escuro com lâmpada falhando",
        "mapa com rota marcada em vermelho",
        "foto rasgada em cima da mesa",
        "câmera de segurança granulado",
        "recorte de jornal antigo",
        "silhueta ao fundo na chuva",
    ]
    cameras = ["close", "wide", "medium", "close", "medium", "close", "wide"]
    return [{"visual_anchor": a, "camera": c} for a, c in zip(anchors, cameras)]


def _normalize_short_dict(d: Dict[str, Any], raw_fallback: str = "") -> Dict[str, Any]:
    if not isinstance(d, dict):
        d = {}

    title = d.get("title")
    if not isinstance(title, str) or not title.strip():
        d["title"] = "Arquivo Oculto (auto)"

    narration = d.get("narration")
    if not isinstance(narration, str):
        d["narration"] = str(raw_fallback or "").strip()
    d["narration"] = re.sub(r"\[PAUSA_FINAL\]\s*$", "", str(d["narration"]).strip(), flags=re.MULTILINE).strip()

    scenes = d.get("scenes")
    if not isinstance(scenes, list):
        scenes = []
    scenes_clean: List[Dict[str, Any]] = []
    for s in scenes:
        if not isinstance(s, dict):
            continue
        va = s.get("visual_anchor")
        cam = s.get("camera")
        scenes_clean.append(
            {
                "visual_anchor": va if isinstance(va, str) and va.strip() else "arquivo",
                "camera": cam if cam in ("wide", "medium", "close") else "medium",
            }
        )

    # Ensure exactly 7
    if len(scenes_clean) < 7:
        padding = _default_short_scenes()
        for i in range(len(scenes_clean), 7):
            scenes_clean.append(padding[i])
    elif len(scenes_clean) > 7:
        scenes_clean = scenes_clean[:7]
    d["scenes"] = scenes_clean

    fq = d.get("final_question")
    if fq is not None and not isinstance(fq, str):
        d["final_question"] = str(fq)

    return d


def generate_short_script() -> Dict[str, Any]:
    """
    Retorna sempre dict válido.
    """
    model = os.getenv("AO_SCRIPT_MODEL", "gpt-4.1-mini")
    temperature = float(os.getenv("AO_SCRIPT_TEMPERATURE", "0.8"))

    schema = """{
  "title": "string",
  "narration": "string (com quebras de linha, 2 linhas finais separadas)",
  "scenes": [ { "visual_anchor": "string", "camera": "wide|medium|close" } x7 ],
  "final_question": "string (opcional)"
}"""

    prompt = (
        "Você é roteirista investigativo cinematográfico. Escreva para TTS (fala natural).\n"
        "Canal: Arquivo Oculto. Estética dark/documental. Tom neutro.\n\n"
        "Objetivo: um SHORT de 45–60s em PT-BR, ritmo alto, frases curtas e visuais.\n"
        "Restrições: não use nomes completos de pessoas reais; não acuse indivíduos reais; evite gore.\n\n"
        "Qualidade obrigatória:\n"
        "1) Narração 130–160 palavras.\n"
        "2) Inclua 3 evidências concretas (sem nomes completos):\n"
        "   - um horário ou data aproximada\n"
        "   - um local genérico verificável\n"
        "   - um detalhe físico (carimbo, foto, fita, etc.)\n"
        "3) Traga 1 contradição específica.\n"
        "4) Final: 2 linhas curtas:\n"
        "   - Linha 1: máx 6 palavras, com ponto.\n"
        "   - Linha 2: pergunta máx 10 palavras, com interrogação.\n\n"
        "Saída: retorne APENAS JSON válido no schema combinado."
    )

    resp = _client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Você cria roteiros curtos documentais (PT-BR) e responde sempre em JSON puro."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )
    raw = (resp.choices[0].message.content or "").strip()
    data = _safe_json_loads(raw)
    if data is None:
        repaired = _repair_to_json(model=model, bad_output=raw, schema=schema)
        data = _safe_json_loads(repaired)

    if data is None:
        data = {"title": "Arquivo Oculto (auto)", "narration": raw, "scenes": _default_short_scenes()}

    return _normalize_short_dict(data, raw_fallback=raw)


# -------------------------
# LONG
# -------------------------
def _get_long_theme() -> str:
    theme = os.getenv("AO_LONG_THEME", "casos_frios").strip().lower()
    aliases = {
        "desaparecimento": "desaparecimentos",
        "desaparecimentos": "desaparecimentos",
        "caso_frio": "casos_frios",
        "casos_frios": "casos_frios",
        "arquivos": "arquivos_militares",
        "arquivos_militares": "arquivos_militares",
        "historico": "eventos_historicos_controversos",
        "eventos_historicos": "eventos_historicos_controversos",
        "eventos_historicos_controversos": "eventos_historicos_controversos",
        "catastrofes": "catastrofes_misteriosas",
        "catastrofes_misteriosas": "catastrofes_misteriosas",
    }
    return aliases.get(theme, theme)


def _compute_long_minutes(target_minutes: float | None) -> float:
    if target_minutes is None:
        try:
            target_minutes = float(os.getenv("AO_LONG_MINUTES", "6.5"))
        except Exception:
            target_minutes = 6.5
    try:
        minutes = float(target_minutes)
    except Exception:
        minutes = 6.5
    return max(1.0, min(20.0, minutes))


def _compute_scenes_count(minutes: float) -> int:
    scenes_env = os.getenv("AO_LONG_SCENES", "").strip()
    if scenes_env:
        try:
            return max(8, min(40, int(scenes_env)))
        except Exception:
            pass
    # ~2.15 cenas/min
    scenes_count = int(round(minutes * 2.15))
    return max(8, min(22, scenes_count))


def _normalize_long_dict(d: Dict[str, Any], scenes_count: int) -> Dict[str, Any]:
    if not isinstance(d, dict):
        d = {}
    d.setdefault("title", "Arquivo Oculto: Caso em Aberto")
    d.setdefault("summary", "")
    d.setdefault("narration", "")
    d.setdefault("thumbnail_prompt", "")

    st = d.get("structure")
    if not isinstance(st, dict):
        st = {}
    st.setdefault("opening_hook", "")
    st.setdefault("official_version", "")
    st.setdefault("timeline_blocks", [])
    st.setdefault("contradictions", [])
    st.setdefault("hypotheses", [])
    st.setdefault("closing_statement", "")
    if not isinstance(st["timeline_blocks"], list):
        st["timeline_blocks"] = []
    if not isinstance(st["contradictions"], list):
        st["contradictions"] = []
    if not isinstance(st["hypotheses"], list):
        st["hypotheses"] = []
    d["structure"] = st

    scenes = d.get("scenes")
    if not isinstance(scenes, list):
        scenes = []

    clean: List[Dict[str, Any]] = []
    for s in scenes:
        if not isinstance(s, dict):
            continue
        clean.append(
            {
                "visual_anchor": str(s.get("visual_anchor") or "").strip()[:60] or "arquivo antigo",
                "location": str(s.get("location") or "").strip()[:60] or "arquivo municipal",
                "era": str(s.get("era") or "").strip()[:30] or "anos 2000",
                "object_focus": str(s.get("object_focus") or "").strip()[:60] or "pasta carimbada",
                "camera": str(s.get("camera") or "wide").strip().lower(),
                "mood": str(s.get("mood") or "archival").strip().lower(),
            }
        )
    for s in clean:
        if s["camera"] not in ("wide", "medium", "close"):
            s["camera"] = "wide"
        if s["mood"] not in ("dark", "neutral", "cold", "archival"):
            s["mood"] = "archival"

    if len(clean) > scenes_count:
        clean = clean[:scenes_count]
    while len(clean) < scenes_count:
        clean.append(
            {
                "visual_anchor": "arquivo antigo",
                "location": "arquivo municipal",
                "era": "anos 2000",
                "object_focus": "pasta carimbada",
                "camera": "close" if (len(clean) % 3 == 0) else "wide",
                "mood": "archival",
            }
        )
    d["scenes"] = clean
    return d


def generate_long_script(target_minutes: float | None = None) -> Dict[str, Any]:
    """
    Retorna sempre dict válido.
    """
    model = os.getenv("AO_LONG_MODEL", os.getenv("AO_SCRIPT_MODEL", "gpt-4.1-mini"))
    temperature = float(os.getenv("AO_LONG_TEMPERATURE", "0.8"))
    theme = _get_long_theme()
    minutes = _compute_long_minutes(target_minutes)
    scenes_count = _compute_scenes_count(minutes)

    closings = [
        "Os registros permanecem abertos.",
        "O arquivo segue incompleto.",
        "Nem todos os documentos vieram à tona.",
        "Algumas respostas continuam ausentes.",
        "O caso permanece encerrado. Nos arquivos, não.",
    ]

    theme_guidance = {
        "desaparecimentos": "desaparecimento documentado, com linha do tempo e últimas evidências (câmeras, bilhetes, registros).",
        "casos_frios": "caso não resolvido com evidências materiais e contradições em relatórios/declarações oficiais.",
        "arquivos_militares": "documentos/arquivos institucionais, memorandos, registros desclassificados (sem citar nomes completos).",
        "eventos_historicos_controversos": "evento histórico com versões conflitantes e documentação incompleta.",
        "catastrofes_misteriosas": "incidente/catástrofe com falhas documentais e inconsistências técnicas (registros, relatórios).",
    }.get(theme, "caso investigativo documental com documentação incompleta e contradições.")

    min_words = int(max(750, minutes * 130))
    max_words = int(max(950, minutes * 170))

    schema = f"""{{
  "title": "string",
  "summary": "string",
  "narration": "string",
  "structure": {{
    "opening_hook": "string",
    "official_version": "string",
    "timeline_blocks": [ {{"label":"string","description":"string","approx_time_reference":"string"}} ],
    "contradictions": [ {{"official_claim":"string","conflicting_record":"string"}} ],
    "hypotheses": ["string"],
    "closing_statement": "string"
  }},
  "scenes": [ {{"visual_anchor":"string","location":"string","era":"string","object_focus":"string","camera":"wide|medium|close","mood":"dark|neutral|cold|archival"}} x{scenes_count} ],
  "thumbnail_prompt": "string"
}}"""

    prompt = (
        "Você é roteirista investigativo cinematográfico (Arquivo Oculto). Escreva para TTS (fala natural, PT-BR).\n"
        "Tom: neutro, preciso, documental. Sem sensacionalismo. Sem acusar indivíduos reais.\n"
        f"Tema editorial: {theme} — {theme_guidance}\n\n"
        "Escolha um caso REAL amplamente conhecido/documentado (Brasil ou mundo), mas:\n"
        "- Evite nomes completos de pessoas reais: use iniciais ou descrições genéricas.\n"
        "- Se houver risco de imprecisão, trate datas como aproximadas e use linguagem cautelosa.\n"
        "- Use elementos documentais plausíveis: datas, horários, locais genéricos verificáveis.\n\n"
        f"Meta: {minutes:.1f} minutos (faixa {min_words}–{max_words} palavras).\n"
        "Estrutura obrigatória:\n"
        "1) Abertura fria (20–40s) com detalhe físico + horário/data.\n"
        "2) Contexto documentado (onde/quando/versão oficial).\n"
        "3) Linha do tempo em 4 a 6 blocos (evento + evidência + local).\n"
        "4) Contradição central (versão oficial vs registro conflitante específico).\n"
        "5) 2–3 hipóteses plausíveis, sem concluir.\n"
        "6) Encerramento com assinatura.\n\n"
        "Coerência visual:\n"
        "- Tudo deve ser gerável em imagem documental (arquivo, papel, mapa, prédio, estrada, fita, foto, carimbo).\n"
        "- Evite abstrações.\n\n"
        f"Gere exatamente {scenes_count} cenas no array scenes.\n\n"
        "Saída: retorne APENAS JSON válido no schema combinado. Escolha UMA assinatura dentre:\n"
        + "\n".join([f"- {c}" for c in closings])
    )

    resp = _client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Você cria roteiros LONG documentais (PT-BR) e responde sempre em JSON puro."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )
    raw = (resp.choices[0].message.content or "").strip()
    data = _safe_json_loads(raw)
    if data is None:
        repaired = _repair_to_json(model=model, bad_output=raw, schema=schema)
        data = _safe_json_loads(repaired)

    data = _normalize_long_dict(data if isinstance(data, dict) else {}, scenes_count=scenes_count)

    st = data.get("structure") or {}
    if isinstance(st, dict) and not str(st.get("closing_statement") or "").strip():
        st["closing_statement"] = closings[0]
        data["structure"] = st

    return data
