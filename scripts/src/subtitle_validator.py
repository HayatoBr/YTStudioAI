# scripts/src/subtitle_validator.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002700-\U000027BF"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)
_WS_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9']+")

# Frases genéricas (muito comuns em roteiros fracos) – removemos no modo STRICT
_GENERIC_PATTERNS = [
    r"NINGUÉM SABE",
    r"ISSO MUDA TUDO",
    r"A VERDADE",
    r"NADA FAZ SENTIDO",
    r"VOCÊ ACREDITA",
    r"VOCÊ ACHA",
    r"UM DETALHE",
    r"ALGO ESTRANHO",
]
_GENERIC_RE = re.compile(r"^(?:%s)$" % "|".join(_GENERIC_PATTERNS), flags=re.IGNORECASE)

# Palavras de evidência (ajuda a garantir “tom documental”)
_EVIDENCE_TOKENS = {
    "ARQUIVO", "REGISTRO", "DOCUMENTO", "CARIMBO", "FITA", "FOTO", "RELATÓRIO",
    "LISTA", "PROTOCOLO", "FICHA", "DATA", "HORÁRIO", "HORA", "MAPA", "LAUDO",
    "CONFIDENCIAL", "OFICIAL", "MUNICIPAL"
}

def _normalize(text: str) -> str:
    text = text.replace("\r", " ").replace("\n", " ")
    text = _EMOJI_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    return text

def _words(text: str) -> List[str]:
    return _WORD_RE.findall(text)

def _to_upper_ptbr(text: str) -> str:
    return text.upper()

def _tokenize_upper(text: str) -> List[str]:
    return [w.upper() for w in _words(_normalize(text))]

def _has_evidence_token(text: str) -> bool:
    toks = set(_tokenize_upper(text))
    return bool(toks & _EVIDENCE_TOKENS)

def _safe_scene_id(scene: Dict[str, Any], fallback: int) -> int:
    try:
        return int(scene.get("scene_id", fallback))
    except Exception:
        return fallback

@dataclass
class SubtitleRules:
    min_words: int = 2
    max_words: int = 5
    max_chars: int = 34
    uppercase: bool = True
    allow_emojis: bool = False

@dataclass
class StrictRules:
    enabled: bool = False
    # repetição
    max_repeat_ratio_scene: float = 0.35  # % de palavras repetidas na mesma cena
    max_same_chunk_duplicates_scene: int = 0  # 0 = proibir duplicatas dentro da cena
    avoid_consecutive_duplicate_chunks: bool = True
    # qualidade
    ban_generic_chunks: bool = True
    require_evidence_in_roles: Tuple[str, ...] = ("evidencia", "contradicao")
    # fallback
    allow_fallback: bool = True

@dataclass
class SubtitleIssue:
    scene_id: int
    chunk_index: int
    code: str
    message: str
    original: str
    fixed: Optional[str] = None

@dataclass
class SubtitleValidationReport:
    ok: bool
    issues: List[SubtitleIssue] = field(default_factory=list)

    def summary(self) -> str:
        if not self.issues:
            return "✅ Legendas validadas: nenhum problema encontrado."
        counts: Dict[str, int] = {}
        for i in self.issues:
            counts[i.code] = counts.get(i.code, 0) + 1
        top = ", ".join([f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))][:8])
        return f"⚠️ Legendas validadas com ajustes: {len(self.issues)} issue(s) ({top})."

def sanitize_chunk_text(text: str, rules: SubtitleRules) -> str:
    t = _normalize(text)
    t = t.strip(" -–—•|/\\")
    if rules.uppercase:
        t = _to_upper_ptbr(t)
    t = re.sub(r"[!?]{2,}", "!", t)
    t = re.sub(r"\.{3,}", "…", t)
    t = t.strip('"').strip("'").strip()
    # soft trim by dropping trailing words
    if len(t) > rules.max_chars:
        w = _words(t)
        while w and len(" ".join(w)) > rules.max_chars:
            w = w[:-1]
        t = " ".join(w).strip() or t[: rules.max_chars].rstrip()
    return t

def enforce_word_count(text: str, rules: SubtitleRules) -> str:
    t = _normalize(text)
    w = _words(t)
    if len(w) > rules.max_words:
        w = w[: rules.max_words]
    t2 = " ".join(w) if w else t
    return _to_upper_ptbr(_normalize(t2)) if rules.uppercase else _normalize(t2)

def _fallback_chunk_for_scene(scene: Dict[str, Any], rules: SubtitleRules) -> str:
    role = (scene.get("narrative_role") or "").strip().lower()
    anchor = (scene.get("visual_anchor") or "").strip().lower()

    # Preferir termos documentais
    if role == "evidencia":
        if "document" in anchor or "evidenc" in anchor or "arquivo" in anchor:
            cand = "REGISTRO OFICIAL"
        else:
            cand = "EVIDÊNCIA NO ARQUIVO"
    elif role == "contradicao":
        cand = "ISSO NÃO BATE"
    elif role == "desfecho":
        cand = "E ISSO FICA AÍ."
    elif role == "gancho":
        cand = "ANOTADO NO ARQUIVO"
    else:
        cand = "DETALHE DOCUMENTADO"

    cand = sanitize_chunk_text(cand, rules)
    cand = enforce_word_count(cand, rules)
    # garantir 2-5 palavras
    w = _words(_normalize(cand))
    if len(w) < rules.min_words:
        cand = " ".join((w + ["AQUI"])[: rules.min_words]) if w else "NO ARQUIVO"
        cand = sanitize_chunk_text(cand, rules)
        cand = enforce_word_count(cand, rules)
    return cand

def validate_and_sanitize_subtitle_chunks(
    data: Dict[str, Any],
    video_type: str,
    rules: Optional[SubtitleRules] = None,
    strict: Optional[StrictRules] = None,
) -> Tuple[Dict[str, Any], SubtitleValidationReport]:
    rules = rules or SubtitleRules()
    strict = strict or StrictRules(enabled=False)
    issues: List[SubtitleIssue] = []

    scenes = data.get("scenes") or []
    if not isinstance(scenes, list):
        return data, SubtitleValidationReport(ok=True, issues=[])

    prev_last_chunk: Optional[str] = None

    for si, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        scene_id = _safe_scene_id(scene, si + 1)
        chunks = scene.get("subtitle_chunks")
        if not chunks or not isinstance(chunks, list):
            continue

        cleaned: List[str] = []
        for ci, raw in enumerate(chunks):
            if not isinstance(raw, str):
                issues.append(SubtitleIssue(scene_id, ci, "non_string", "Chunk não é string; removido.", str(raw), fixed=None))
                continue

            orig = raw
            t = sanitize_chunk_text(orig, rules)

            if not rules.allow_emojis and _EMOJI_RE.search(orig or ""):
                issues.append(SubtitleIssue(scene_id, ci, "emoji_removed", "Emoji removido.", orig, fixed=t))

            # Word count
            if len(_words(_normalize(t))) > rules.max_words:
                t2 = enforce_word_count(t, rules)
                issues.append(SubtitleIssue(scene_id, ci, "too_many_words", f"> {rules.max_words} palavras; truncado.", orig, fixed=t2))
                t = t2

            # Char limit
            if len(t) > rules.max_chars:
                t2 = sanitize_chunk_text(t, rules)
                if len(t2) < len(t):
                    issues.append(SubtitleIssue(scene_id, ci, "too_many_chars", f"> {rules.max_chars} chars; encurtado.", orig, fixed=t2))
                t = t2

            if not t.strip():
                issues.append(SubtitleIssue(scene_id, ci, "empty", "Chunk vazio; removido.", orig, fixed=None))
                continue

            cleaned.append(t)

        # Merge chunks with too few words
        merged: List[str] = []
        i = 0
        while i < len(cleaned):
            cur = cleaned[i]
            if len(_words(_normalize(cur))) < rules.min_words and i + 1 < len(cleaned):
                nxt = cleaned[i + 1]
                merged_text = sanitize_chunk_text((cur + " " + nxt).strip(), rules)
                merged_text = enforce_word_count(merged_text, rules)
                issues.append(SubtitleIssue(scene_id, i, "too_few_words", f"< {rules.min_words} palavras; mesclado com próximo.", cur, fixed=merged_text))
                merged.append(merged_text)
                i += 2
            else:
                merged.append(cur)
                i += 1

        # STRICT: remove genéricos e duplicatas
        if strict.enabled:
            deduped: List[str] = []
            seen: Dict[str, int] = {}
            for ci, t in enumerate(merged):
                tn = _normalize(t).upper()

                if strict.ban_generic_chunks and _GENERIC_RE.match(tn):
                    issues.append(SubtitleIssue(scene_id, ci, "generic_banned", "Chunk genérico banido (STRICT).", t, fixed=None))
                    continue

                if strict.max_same_chunk_duplicates_scene == 0:
                    if tn in seen:
                        issues.append(SubtitleIssue(scene_id, ci, "duplicate_in_scene", "Chunk duplicado na cena (STRICT); removido.", t, fixed=None))
                        continue
                seen[tn] = seen.get(tn, 0) + 1
                deduped.append(t)

            merged = deduped

            # Avoid consecutive duplicates across scenes
            if strict.avoid_consecutive_duplicate_chunks and prev_last_chunk and merged:
                if _normalize(merged[0]).upper() == _normalize(prev_last_chunk).upper():
                    issues.append(SubtitleIssue(scene_id, 0, "duplicate_consecutive", "Chunk repetido em cenas consecutivas; removido.", merged[0], fixed=None))
                    merged = merged[1:]

            # Repetition ratio within scene (word-level)
            all_words = []
            for t in merged:
                all_words += _tokenize_upper(t)
            if all_words:
                uniq = set(all_words)
                repeat_ratio = 1.0 - (len(uniq) / max(1, len(all_words)))
                if repeat_ratio > strict.max_repeat_ratio_scene:
                    issues.append(SubtitleIssue(scene_id, -1, "high_repetition", f"Muita repetição na cena (ratio={repeat_ratio:.2f}); recomendado simplificar.", " ".join(merged), fixed=None))

            # Require evidence token for certain roles
            role = (scene.get("narrative_role") or "").strip().lower()
            if role in strict.require_evidence_in_roles:
                has_any = any(_has_evidence_token(t) for t in merged)
                if not has_any:
                    if strict.allow_fallback:
                        fb = _fallback_chunk_for_scene(scene, rules)
                        issues.append(SubtitleIssue(scene_id, -1, "missing_evidence_token", "Cena exige termo documental; inserido fallback (STRICT).", "", fixed=fb))
                        merged = [fb] + merged[: max(0, (rules.max_words and 10))]  # keep short; fallback first
                    else:
                        issues.append(SubtitleIssue(scene_id, -1, "missing_evidence_token", "Cena exige termo documental; nenhum fallback permitido.", " ".join(merged), fixed=None))

        # Final clamp: drop empty and ensure max_words per chunk still ok
        final_chunks: List[str] = []
        for ci, t in enumerate(merged):
            t2 = sanitize_chunk_text(t, rules)
            t2 = enforce_word_count(t2, rules)
            if t2.strip():
                final_chunks.append(t2)

        scene["subtitle_chunks"] = final_chunks
        prev_last_chunk = final_chunks[-1] if final_chunks else prev_last_chunk

    return data, SubtitleValidationReport(ok=True, issues=issues)

# Backward-compatible name used by orchestrator in earlier patches
def validate_and_sanitize_subtitle_chunks_compat(
    short_or_long_data: Dict[str, Any],
    video_type: str,
    rules: Optional[SubtitleRules] = None,
) -> Tuple[Dict[str, Any], SubtitleValidationReport]:
    return validate_and_sanitize_subtitle_chunks(short_or_long_data, video_type=video_type, rules=rules, strict=StrictRules(enabled=False))

# Compat: nome esperado pelo orchestrator/CLI
def validate_subtitles(short_or_long_data: Dict[str, Any], strict: bool = False, video_type: str = "short") -> SubtitleValidationReport:
    """Valida e sanitiza subtitle_chunks. Retorna um report; também modifica o JSON in-place."""
    rules = SubtitleRules()
    strict_rules = StrictRules(enabled=bool(strict))
    _, report = validate_and_sanitize_subtitle_chunks(short_or_long_data, video_type=video_type, rules=rules, strict=strict_rules)
    return report

