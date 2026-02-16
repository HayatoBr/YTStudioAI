# scripts/src/openai_generators.py
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Union

from openai import OpenAI

# OpenAI client reads OPENAI_API_KEY from environment by default
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _extract_json_candidate(text: str) -> Optional[str]:
    """
    Extract a plausible JSON object from a model response that may include extra text.
    Returns the JSON string if found, else None.
    """
    if not text:
        return None
    s = text.strip()

    # Fast path: looks like pure JSON
    if s.startswith("{") and s.endswith("}"):
        return s

    # Remove fenced code blocks if any
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"\s*```$", "", s).strip()

    # Best-effort: take outermost braces
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


def _default_scenes() -> List[Dict[str, Any]]:
    # 7 cenas padrão “Arquivo Oculto”
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


def _normalize_script_dict(d: Dict[str, Any], raw_fallback: str = "") -> Dict[str, Any]:
    title = d.get("title")
    narration = d.get("narration")
    scenes = d.get("scenes")

    if not isinstance(title, str) or not title.strip():
        d["title"] = "Arquivo Oculto (auto)"

    if not isinstance(narration, str):
        # fallback to raw text if model didn't comply
        d["narration"] = str(raw_fallback or "").strip()

    # Remove any legacy placeholders that should NEVER reach subtitles
    # (your subtitle_from_script now strips/ignores these, but we keep it clean here too)
    d["narration"] = re.sub(r"\[PAUSA_FINAL\]\s*$", "", d["narration"].strip(), flags=re.MULTILINE).strip()

    # Scenes: keep for visual system; subtitles are generated from narration elsewhere
    if not isinstance(scenes, list):
        scenes = []
    scenes_clean: List[Dict[str, Any]] = []
    for s in scenes:
        if not isinstance(s, dict):
            continue
        va = s.get("visual_anchor")
        cam = s.get("camera")
        item = {
            "visual_anchor": va if isinstance(va, str) and va.strip() else "arquivo",
            "camera": cam if cam in ("wide", "medium", "close") else "medium",
        }
        # Preserve extra keys if you use them later (e.g., mood, negative_prompt)
        for k, v in s.items():
            if k in item:
                continue
            item[k] = v
        scenes_clean.append(item)

    # Ensure exactly 7 scenes
    if len(scenes_clean) < 7:
        padding = _default_scenes()
        # fill remaining with defaults
        for i in range(len(scenes_clean), 7):
            scenes_clean.append(padding[i])
    elif len(scenes_clean) > 7:
        scenes_clean = scenes_clean[:7]

    d["scenes"] = scenes_clean

    # Optional field: final_question
    fq = d.get("final_question")
    if fq is not None and not isinstance(fq, str):
        d["final_question"] = str(fq)

    return d


def _repair_to_json(model: str, bad_output: str) -> str:
    """
    Second-pass repair: ask the model to output valid JSON only.
    Keep temperature low to maximize compliance.
    """
    repair_prompt = (
        "Converta o conteúdo abaixo em APENAS um JSON válido (sem markdown, sem texto extra), "
        "seguindo este schema:\n"
        "{\n"
        '  "title": "string",\n'
        '  "narration": "string",\n'
        '  "scenes": [ { "visual_anchor": "string", "camera": "wide|medium|close" } x7 ],\n'
        '  "final_question": "string (opcional)"\n'
        "}\n\n"
        "Conteúdo:\n"
        + bad_output
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Você é um conversor rigoroso para JSON válido."},
            {"role": "user", "content": repair_prompt},
        ],
        temperature=0.1,
    )
    return (resp.choices[0].message.content or "").strip()


def generate_short_script() -> Dict[str, Any]:
    """
    Gera roteiro curto para o canal Arquivo Oculto.
    CONTRATO: sempre retorna um dict válido (nunca string).
    """
    model = os.getenv("AO_SCRIPT_MODEL", "gpt-4.1-mini")

    # Prompt cinematográfico + investigativo (TikTok pacing), sem placeholders de "pausa final"
    prompt = (
        "Você é roteirista investigativo cinematográfico. Escreva para TTS (fala natural).\n"
        "Canal: Arquivo Oculto. Estética dark/documental.\n\n"
        "Objetivo: um SHORT de 45–60s em PT-BR, ritmo alto, frases curtas e visuais.\n"
        "Restrições: não use nomes reais, não acuse pessoas reais; evite gore explícito.\n\n"
        "Regras obrigatórias de qualidade:\n"
        "1) Narração entre 130 e 160 palavras.\n"
        "2) Inclua 3 evidências concretas (sem nomes):\n"
        "   - um horário ou data aproximada (ex: 'por volta das 2h', 'no fim de 2001')\n"
        "   - um local genérico verificável (ex: 'estação', 'arquivo municipal', 'rodovia')\n"
        "   - um detalhe físico (ex: 'carimbo CONFIDENCIAL', 'foto rasgada', 'fita')\n"
        "3) Traga 1 contradição específica (algo que não bate).\n"
        "4) Use reticências '…' apenas quando mudar de ideia (poucas vezes).\n"
        "5) Final: 2 linhas curtas:\n"
        "   - Linha 1: frase curta (máx 6 palavras), com ponto.\n"
        "   - Linha 2: pergunta curta (máx 10 palavras), com interrogação.\n\n"
        "Estrutura sugerida:\n"
        "- 0–3s: gancho com dado concreto\n"
        "- 3–12s: contexto rápido\n"
        "- 12–40s: 3 evidências (1 por bloco)\n"
        "- 40–52s: contradição e hipótese\n"
        "- 52–60s: fechamento + pergunta\n\n"
        "Saída: retorne APENAS um JSON válido (sem markdown), exatamente neste formato:\n"
        "{\n"
        '  "title": "…",\n'
        '  "narration": "texto com quebras de linha\\n(2 linhas finais separadas)",\n'
        '  "scenes": [\n'
        '    {"visual_anchor": "…", "camera": "wide|medium|close"},\n'
        "    ... (exatamente 7 itens)\n"
        "  ],\n"
        '  "final_question": "a mesma pergunta da narração"\n'
        "}\n"
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Você cria roteiros investigativos curtos com evidências concretas e ritmo cinematográfico.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=float(os.getenv("AO_SCRIPT_TEMPERATURE", "0.8")),
    )

    raw = (response.choices[0].message.content or "").strip()

    data = _safe_json_loads(raw)

    # One repair attempt if invalid
    if data is None:
        repaired = _repair_to_json(model=model, bad_output=raw)
        data = _safe_json_loads(repaired)

    if data is None:
        # Hard fallback: return dict anyway
        data = {
            "title": "Arquivo Oculto (auto)",
            "narration": raw,
            "scenes": _default_scenes(),
        }

    return _normalize_script_dict(data, raw_fallback=raw)


# =========================
# LONGS (5–8 min) — Arquivo Oculto
# =========================

def _get_long_theme() -> str:
    """Tema editorial do LONG definido por ENV (controla o tipo de caso)."""
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


def _normalize_long_dict(d: Dict[str, Any], scenes_count: int) -> Dict[str, Any]:
    if not isinstance(d, dict):
        d = {}

    d.setdefault("title", "Arquivo Oculto: Caso em Aberto")
    d.setdefault("summary", "")
    d.setdefault("narration", "")
    d.setdefault("thumbnail_prompt", "")

    # structure
    st = d.get("structure")
    if not isinstance(st, dict):
        st = {}
    st.setdefault("opening_hook", "")
    st.setdefault("official_version", "")
    st.setdefault("timeline_blocks", [])
    st.setdefault("contradictions", [])
    st.setdefault("hypotheses", [])
    st.setdefault("closing_statement", "")

    # normalize arrays
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

    # clean each scene
    clean = []
    for s in scenes:
        if not isinstance(s, dict):
            continue
        clean.append(
            {
                "visual_anchor": str(s.get("visual_anchor") or "").strip()[:60] or "arquivo antigo",
                "location": str(s.get("location") or "").strip()[:60] or "arquivo municipal",
                "era": str(s.get("era") or "").strip()[:30] or "anos 2000",
                "object_focus": str(s.get("object_focus") or "").strip()[:60] or "pasta carimbada",
                "camera": (str(s.get("camera") or "wide").strip().lower() if str(s.get("camera") or "") else "wide"),
                "mood": (str(s.get("mood") or "archival").strip().lower() if str(s.get("mood") or "") else "archival"),
            }
        )

    # clamp camera/mood
    for s in clean:
        if s["camera"] not in ("wide", "medium", "close"):
            s["camera"] = "wide"
        if s["mood"] not in ("dark", "neutral", "cold", "archival"):
            s["mood"] = "archival"

    # enforce count
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


def _repair_long_to_json(model: str, bad_output: str, scenes_count: int) -> str:
    """Second-pass repair para LONG: força JSON puro no schema do LONG."""
    repair_prompt = (
        "Converta o conteúdo abaixo em APENAS um JSON válido (sem markdown, sem texto extra), "
        "seguindo este schema:\\n"
        "{\\n"
        '  "title": "string",\\n'
        '  "summary": "string",\\n'
        '  "narration": "string",\\n'
        '  "structure": {\\n'
        '    "opening_hook": "string",\\n'
        '    "official_version": "string",\\n'
        '    "timeline_blocks": [ {"label":"string","description":"string","approx_time_reference":"string"} ],\\n'
        '    "contradictions": [ {"official_claim":"string","conflicting_record":"string"} ],\\n'
        '    "hypotheses": ["string"],\\n'
        '    "closing_statement": "string"\\n'
        "  },\\n"
        f'  "scenes": [ {{"visual_anchor":"string","location":"string","era":"string","object_focus":"string","camera":"wide|medium|close","mood":"dark|neutral|cold|archival"}} x{scenes_count} ],\\n'
        '  "thumbnail_prompt": "string"\\n'
        "}\\n\\n"
        "Conteúdo:\\n"
        + bad_output
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Você é um reparador de JSON. Retorne somente JSON válido."},
            {"role": "user", "content": repair_prompt},
        ],
        temperature=0.0,
    )
    return resp.choices[0].message.content or ""


def generate_long_script() -> Dict[str, Any]:
    """
    Gera roteiro LONG (5–8 min) para o canal Arquivo Oculto.
    A IA escolhe um caso real dentro do nicho definido por AO_LONG_THEME.
    CONTRATO: sempre retorna um dict válido (nunca string).
    """
    model = os.getenv("AO_LONG_MODEL", os.getenv("AO_SCRIPT_MODEL", "gpt-4.1-mini"))
    theme = _get_long_theme()

    # duração/escopo
    try:
        minutes = float(os.getenv("AO_LONG_MINUTES", "6.5"))
    except Exception:
        minutes = 6.5
    minutes = max(4.5, min(10.0, minutes))

    try:
        scenes_count = int(os.getenv("AO_LONG_SCENES", "14"))
    except Exception:
        scenes_count = 14
    scenes_count = max(12, min(18, scenes_count))

    # fechamento (IA escolhe 1)
    closings = [
        "Os registros permanecem abertos.",
        "O arquivo segue incompleto.",
        "Nem todos os documentos vieram à tona.",
        "Algumas respostas continuam ausentes.",
        "O caso permanece encerrado. Nos arquivos, não.",
    ]

    theme_guidance = {
        "desaparecimentos": "desaparecimento documentado, com linha do tempo e últimas evidências (câmeras, bilhetes, registros de transporte).",
        "casos_frios": "caso não resolvido com evidências materiais e contradições em relatórios/declarações oficiais.",
        "arquivos_militares": "documentos/arquivos institucionais, memorandos, registros desclassificados (sem citar nomes completos).",
        "eventos_historicos_controversos": "evento histórico com versões conflitantes e documentação incompleta.",
        "catastrofes_misteriosas": "incidente/catástrofe com falhas documentais e inconsistências técnicas (registros, relatórios).",
    }.get(theme, "caso investigativo documental com documentação incompleta e contradições.")

    # palavras alvo (fala)
    min_words = int(max(750, minutes * 130))
    max_words = int(max(950, minutes * 170))

    prompt = (
        "Você é roteirista investigativo cinematográfico (Arquivo Oculto). Escreva para TTS (fala natural, PT-BR).\\n"
        "Tom: neutro, preciso, documental. Sem sensacionalismo. Sem acusar indivíduos reais.\\n"
        f"Tema editorial (AO_LONG_THEME): {theme} — {theme_guidance}\\n\\n"
        "Escolha um caso REAL amplamente conhecido/documentado (Brasil ou mundo), mas:\\n"
        "- Não use nomes completos de pessoas reais. Se mencionar, use iniciais ou descrições genéricas.\\n"
        "- Se houver risco de imprecisão, trate datas como aproximadas e use linguagem: 'registros públicos indicam', 'relatórios apontam'.\\n"
        "- Use elementos documentais plausíveis: datas, horários, locais genéricos verificáveis, números de protocolo fictícios, carimbos e transcrições curtas.\\n\\n"
        f"Meta: {minutes} minutos (faixa de {min_words} a {max_words} palavras).\\n"
        "Estrutura obrigatória (não escreva rótulos):\\n"
        "1) Abertura fria (20–40s) com detalhe físico + horário/data e tensão documental.\\n"
        "2) Contexto documentado (onde/quando/versão oficial).\\n"
        "3) Linha do tempo em 4 a 6 blocos, cada um com: evento + evidência concreta + local.\\n"
        "4) Contradição central: versão oficial vs registro conflitante (específico).\\n"
        "5) Hipóteses plausíveis (2–3), sem afirmar conclusões.\\n"
        "6) Encerramento com assinatura (a IA escolhe uma variação).\\n\\n"
        "Coerência visual (muito importante):\\n"
        "- Tudo deve ser gerável em imagem documental (arquivo, papel, mapa, prédio, estrada, fita, foto, carimbo).\\n"
        "- Evite elementos abstratos.\\n\\n"
        f"Cenas: gere exatamente {scenes_count} cenas.\\n"
        "- visual_anchor: 2–6 palavras, sempre concreto.\\n"
        "- location: curto e específico.\\n"
        "- era: ano ou década aproximada.\\n"
        "- object_focus: objeto principal.\\n"
        "- camera: wide|medium|close.\\n"
        "- mood: dark|neutral|cold|archival.\\n\\n"
        "Saída: retorne APENAS JSON válido (sem markdown) neste formato:\\n"
        "{\\n"
        '  "title": "…",\\n'
        '  "summary": "…",\\n'
        '  "narration": "…",\\n'
        '  "structure": {\\n'
        '    "opening_hook": "…",\\n'
        '    "official_version": "…",\\n'
        '    "timeline_blocks": [{"label":"…","description":"…","approx_time_reference":"…"}],\\n'
        '    "contradictions": [{"official_claim":"…","conflicting_record":"…"}],\\n'
        '    "hypotheses": ["…"],\\n'
        '    "closing_statement": "…"\\n'
        "  },\\n"
        '  "scenes": [{"visual_anchor":"…","location":"…","era":"…","object_focus":"…","camera":"wide|medium|close","mood":"dark|neutral|cold|archival"}],\\n'
        '  "thumbnail_prompt": "…"\\n'
        "}\\n\\n"
        "Escolha UMA assinatura dentre estas opções (pode adaptar levemente):\\n"
        + "\\n".join([f"- {c}" for c in closings])
        + "\\n"
        "Regras finais: JSON puro; não inclua 'pausa final' nem '...'.\\n"
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Você cria roteiros LONG (PT-BR) com estética documental e tom neutro. Responda sempre em JSON puro."},
            {"role": "user", "content": prompt},
        ],
        temperature=float(os.getenv("AO_LONG_TEMPERATURE", "0.8")),
    )

    raw = resp.choices[0].message.content or ""
    data = _safe_json_loads(raw)

    if not isinstance(data, dict):
        fixed = _repair_long_to_json(model, raw, scenes_count=scenes_count)
        data = _safe_json_loads(fixed)

    data = _normalize_long_dict(data if isinstance(data, dict) else {}, scenes_count=scenes_count)

    # garante assinatura se vazia
    st = data.get("structure") or {}
    if isinstance(st, dict):
        if not str(st.get("closing_statement") or "").strip():
            st["closing_statement"] = closings[0]
        data["structure"] = st

    return data
