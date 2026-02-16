# scripts/src/visual_templates.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)
class VisualPromptTemplates:
    base: str = (
        "Imagem no estilo documental investigativo.\n\n"
        "Ambiente: {environment}\n"
        "Objeto principal: {primary_object}\n"
        "Objeto secundário: {secondary_object}\n\n"
        "Iluminação: baixa, dramática, lateral\n"
        "Clima emocional: {emotion}\n"
        "Paleta de cores: fria, dessaturada\n"
        "Textura: fotografia de arquivo, grão sutil\n\n"
        "Composição:\n"
        "- Objeto principal em destaque\n"
        "- Fundo levemente desfocado\n"
        "- Sem texto legível\n"
        "- Sem pessoas visíveis (exceto silhuetas desfocadas se permitido)\n\n"
        "Restrições:\n"
        "- Não gerar rostos humanos nítidos\n"
        "- Não incluir elementos modernos\n"
        "- Não exagerar efeitos cinematográficos\n"
    )

    short: str = (
        "Imagem realista, documental, para vídeo curto investigativo.\n"
        "Ambiente: {environment}\n"
        "Elemento central: {primary_object}\n"
        "Detalhe secundário: {secondary_object}\n\n"
        "Iluminação baixa e contrastada.\n"
        "Cores frias e pouco saturadas.\n"
        "Plano médio ou close. Fundo neutro. Sem distrações.\n"
        "Sem pessoas visíveis. Sem texto legível."
    )

    long: str = (
        "Imagem altamente realista no estilo documental investigativo para documentário longo.\n\n"
        "Ambiente detalhado: {environment}\n"
        "Objeto principal: {primary_object}\n"
        "Elementos secundários: {secondary_object}\n\n"
        "Iluminação baixa, direcional, sombras suaves.\n"
        "Atmosfera: tensa, silenciosa, investigativa.\n"
        "Paleta: tons frios, baixa saturação, contraste moderado.\n"
        "Profundidade de campo e camadas visuais claras.\n"
        "Sem pessoas identificáveis. Sem texto legível. Sem exageros cinematográficos."
    )

    fallback: str = (
        "Imagem simbólica no estilo documental investigativo.\n"
        "Elemento central: pasta de arquivo ou documento genérico com carimbo CONFIDENCIAL.\n"
        "Ambiente: sala de arquivos escura.\n"
        "Iluminação baixa. Cores frias e dessaturadas. Atmosfera silenciosa.\n"
        "Composição simples. Sem pessoas. Sem texto legível."
    )

    close: str = (
        "Close-up realista no estilo documental investigativo.\n"
        "Objeto: {primary_object}\n"
        "Detalhe visível: {secondary_object}\n"
        "Iluminação lateral baixa. Fundo desfocado. Cores frias.\n"
        "Sem pessoas. Sem texto legível."
    )

    parallax: str = (
        "Imagem realista adequada para parallax simples (camadas).\n"
        "Primeiro plano: {primary_object}\n"
        "Plano intermediário: {secondary_object}\n"
        "Plano de fundo: {environment}\n"
        "Separação clara entre planos. Iluminação consistente.\n"
        "Estilo documental investigativo. Cores frias, dessaturadas.\n"
        "Sem pessoas visíveis. Sem texto legível."
    )

TEMPLATES = VisualPromptTemplates()

def render_template(template: str, params: Dict[str, str]) -> str:
    # Garantir chaves sempre presentes
    safe = {
        "environment": params.get("environment", "sala de arquivos"),
        "primary_object": params.get("primary_object", "pasta de arquivo"),
        "secondary_object": params.get("secondary_object", "carimbo CONFIDENCIAL"),
        "emotion": params.get("emotion", "tenso"),
    }
    return template.format(**safe)
