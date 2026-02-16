# scripts/src/visual_dna.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

# DNA Visual do canal "Arquivo Oculto"
# Objetivo: consistência + reduzir erro/custo na geração de imagens

@dataclass(frozen=True)
class ChannelVisualDNA:
    name: str = "Arquivo Oculto"
    style: str = "documental_investigativo"
    palette: str = "frias_dessaturadas"
    lighting: str = "baixa_dramatica_lateral"
    texture: str = "fotografia_de_arquivo_grao_sutil"
    allow_faces: bool = False  # nunca rostos nítidos
    allow_people: bool = True  # apenas silhuetas desfocadas quando necessário

    # Mapeamentos (conceito -> símbolo visual)
    concept_to_symbol: Dict[str, str] = None  # type: ignore
    # Ambientes canônicos
    environments: List[str] = None  # type: ignore
    # Objetos canônicos (âncoras)
    objects: List[str] = None  # type: ignore

    def __post_init__(self):
        object.__setattr__(self, "concept_to_symbol", {
            "arquivo_oculto": "pasta de arquivo com carimbo CONFIDENCIAL",
            "misterio": "gaveta entreaberta com luz baixa",
            "evidencia": "documento com carimbo OFICIAL",
            "contradicao": "papel rasgado sobre registros",
            "silencio": "sala vazia com sombra longa",
            "registro": "livro de protocolo com fichas",
            "omissao": "texto coberto por tarja preta",
            "desaparecimento": "estrada vazia à noite",
        })
        object.__setattr__(self, "environments", [
            "sala de arquivos",
            "arquivo municipal",
            "corredor escuro",
            "prédio antigo",
            "sala vazia",
            "estrada vazia à noite",
            "mesa de investigação",
        ])
        object.__setattr__(self, "objects", [
            "pasta de arquivo",
            "documento",
            "foto antiga",
            "fita cassete",
            "carimbo CONFIDENCIAL",
            "papel rasgado",
            "relógio antigo",
            "mapa dobrado",
        ])

DNA = ChannelVisualDNA()
