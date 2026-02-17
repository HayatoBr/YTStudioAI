# scripts/src/rag_wiki.py
from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import urllib.parse
import urllib.request


USER_AGENT = os.getenv("AO_RAG_USER_AGENT", "YTStudioAI/1.0 (contact: local)")


def _http_get(url: str, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _wiki_api(lang: str, params: Dict[str, str]) -> Dict[str, Any]:
    base = f"https://{lang}.wikipedia.org/w/api.php"
    params2 = {"format": "json", "formatversion": "2"} | params
    url = base + "?" + urllib.parse.urlencode(params2)
    raw = _http_get(url)
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


def wiki_search(lang: str, query: str, limit: int = 8) -> List[Dict[str, Any]]:
    data = _wiki_api(lang, {"action": "query", "list": "search", "srsearch": query, "srlimit": str(limit)})
    items = (((data or {}).get("query") or {}).get("search") or [])
    out: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "").strip()
        snippet = re.sub(r"<.*?>", "", str(it.get("snippet") or ""))
        if title:
            out.append({"title": title, "snippet": snippet})
    return out


def wiki_extract(lang: str, title: str, chars: int = 2500) -> str:
    # Intro extract (plain text)
    data = _wiki_api(
        lang,
        {
            "action": "query",
            "prop": "extracts",
            "explaintext": "1",
            "exintro": "1",
            "titles": title,
        },
    )
    pages = ((data.get("query") or {}).get("pages") or [])
    if pages and isinstance(pages[0], dict):
        text = str(pages[0].get("extract") or "")
        return text.strip()[:chars]
    return ""


def wiki_page_url(lang: str, title: str) -> str:
    # canonical URL
    t = title.replace(" ", "_")
    return f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(t)}"


def _theme_query(theme: str) -> str:
    theme = (theme or "").strip().lower()
    mapping = {
        "desaparecimentos": "desaparecimento caso não resolvido",
        "casos_frios": "cold case unsolved mystery",
        "arquivos_militares": "documentos desclassificados incidente misterioso",
        "eventos_historicos_controversos": "historical controversy disputed event",
        "catastrofes_misteriosas": "mysterious disaster incident investigation",
    }
    return mapping.get(theme, "unsolved mystery investigation")


def build_case_dossier(
    theme: str,
    prefer_langs: Optional[List[str]] = None,
    max_chars_per_lang: int = 2500,
    pick_strategy: str = "random_top",
) -> Dict[str, Any]:
    """
    Builds a small factual dossier from Wikipedia (optionally 2 languages).
    This is designed for *fallback* script generation (Ollama) to reduce fictitious content.

    Returns dict:
      {
        "query": "...",
        "picked_title": "...",
        "sources": [ { "lang": "en", "title": "...", "url": "...", "extract": "..." }, ... ],
        "notes": "...",
      }
    """
    langs = prefer_langs or [x.strip() for x in os.getenv("AO_RAG_LANGS", "pt,en").split(",") if x.strip()]
    if not langs:
        langs = ["pt", "en"]

    query = _theme_query(theme)
    # Search in the first language as the "selector"
    selector_lang = langs[0]
    results = wiki_search(selector_lang, query, limit=int(os.getenv("AO_RAG_SEARCH_LIMIT", "10")))
    if not results:
        # last resort: broader query
        results = wiki_search(selector_lang, "mistério não resolvido", limit=10)

    picked = results[0]["title"] if results else "Mistério"
    if results and pick_strategy == "random_top":
        topn = max(1, min(len(results), int(os.getenv("AO_RAG_PICK_TOPN", "6"))))
        picked = random.choice(results[:topn])["title"]

    sources: List[Dict[str, Any]] = []
    for lang in langs:
        extract = wiki_extract(lang, picked, chars=max_chars_per_lang)
        if extract:
            sources.append(
                {
                    "lang": lang,
                    "title": picked,
                    "url": wiki_page_url(lang, picked),
                    "extract": extract,
                }
            )

    notes = (
        "Use apenas fatos presentes nos EXTRACTS acima. "
        "Se um detalhe não estiver nos textos, trate como desconhecido ou omita. "
        "Evite nomes completos de pessoas reais; use iniciais quando necessário."
    )

    return {
        "query": query,
        "picked_title": picked,
        "sources": sources,
        "notes": notes,
    }


def dossier_to_prompt(dossier: Dict[str, Any]) -> str:
    """
    Converts dossier dict to a compact prompt block (safe to paste into LLM).
    """
    if not isinstance(dossier, dict):
        return ""

    lines: List[str] = []
    lines.append("DOSSIÊ (fontes Wikipedia):")
    q = dossier.get("query")
    if q:
        lines.append(f"- consulta: {q}")
    t = dossier.get("picked_title")
    if t:
        lines.append(f"- título selecionado: {t}")

    srcs = dossier.get("sources") or []
    for s in srcs:
        if not isinstance(s, dict):
            continue
        lang = s.get("lang") or "?"
        url = s.get("url") or ""
        extract = (s.get("extract") or "").strip()
        if extract:
            lines.append(f"\n[FONTE {lang}] {url}\n{extract}\n")

    notes = dossier.get("notes") or ""
    if notes:
        lines.append(f"\nREGRAS:\n{notes}")

    return "\n".join(lines).strip()
