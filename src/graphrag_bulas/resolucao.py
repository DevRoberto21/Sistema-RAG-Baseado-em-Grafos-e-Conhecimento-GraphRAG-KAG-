"""Resolução de entidades (E4.1, E4.2): extracoes.jsonl -> grafo.jsonl.

Uso:
  uv run --extra embeddings python -m graphrag_bulas.resolucao

Três passos por label: regra (normalizar), dicionário curado (data/curadoria/sinonimos.json)
e similaridade de embedding com limiar. Grava data/processed/grafo.jsonl,
logs/pares_candidatos.csv e a primeira parte de logs/relatorio_e4.md.
Spec: docs/superpowers/specs/2026-11-01-e4-resolucao-ingestao-design.md
"""

import json
import re
from pathlib import Path

from graphrag_bulas.chunks import PROCESSADOS, slug
from graphrag_bulas.extracao import COMPOSICAO

RAIZ = PROCESSADOS.parents[1]
DICIONARIO = RAIZ / "data" / "curadoria" / "sinonimos.json"
ROTULADOS = RAIZ / "data" / "curadoria" / "pares_rotulados.csv"
ENTRADA = PROCESSADOS / "extracoes.jsonl"
SAIDA = PROCESSADOS / "grafo.jsonl"
PARES = RAIZ / "logs" / "pares_candidatos.csv"
RELATORIO = RAIZ / "logs" / "relatorio_e4.md"

LIMIAR_PADRAO = 0.92
FAIXA_PARES = (0.80, 0.95)
SEM_EMBEDDING = {"Medicamento", "Populacao", "Fabricante"}  # vocabulário fechado

GRAFIA = {
    "inhibidor": "inibidor",
    "inhibidores": "inibidores",
    "sistematico": "sistemico",
    "sistematicos": "sistemicos",
}
SAL_PREFIXO = re.compile(
    r"^(cloridrato|dicloridrato|maleato|carbonato|besilato|sulfato|fosfato|succinato|"
    r"tartarato|acetato|citrato|mesilato)_de_"
)
SAL_SUFIXO = re.compile(
    r"_(potassica|potassico|sodica|sodico|calcica|calcico|magnesica|medoxomila|"
    r"monoidratad[ao]|di_?hidratad[ao]|tri_?hidratad[ao])$"
)
OPOSTOS = [("hiper", "hipo"), ("bradi", "taqui"), ("aumento", "diminuicao"), ("aumento", "reducao")]


def _singular(p: str) -> str:
    if p.endswith(("res", "zes")):
        return p[:-2]
    if p.endswith("ais"):
        return p[:-3] + "al"
    if p.endswith("s") and not p.endswith("ss") and len(p) > 2:
        return p[:-1]
    return p


def normalizar(id_: str, label: str) -> str:
    """Regras do E4.1: grafia; sal em PrincipioAtivo; singular em ClasseTerapeutica."""
    partes = [GRAFIA.get(p, p) for p in slug(id_).split("_")]
    if label == "ClasseTerapeutica":
        partes = [_singular(p) for p in partes]
    id_ = "_".join(partes)
    if label == "PrincipioAtivo":
        id_ = SAL_SUFIXO.sub("", SAL_PREFIXO.sub("", id_))
    return id_


def bloqueado(a: str, b: str) -> bool:
    """Nomes com prefixo de sentido oposto (hipertensao/hipotensao) nunca se fundem."""
    return any((x in a and y in b) or (y in a and x in b) for x, y in OPOSTOS)


def carregar_dicionario(path: Path = DICIONARIO) -> dict[str, dict[str, str]]:
    """{label: {variante normalizada: id canônico}}. Inclui nome comercial -> princípio ativo."""
    bruto = json.loads(path.read_text())
    bruto.setdefault("PrincipioAtivo", {})
    for med, pas in COMPOSICAO.items():
        if len(pas) == 1:
            bruto["PrincipioAtivo"].setdefault(pas[0], []).append(med)
    dic = {}
    for label, grupos in bruto.items():
        dic[label] = {}
        for canon, variantes in grupos.items():
            for v in [canon, *variantes]:
                dic[label][normalizar(v, label)] = canon
    return dic
