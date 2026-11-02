"""Ingestão no Neo4j (E4.3, E4.4): grafo.jsonl + documentos -> Neo4j.

Uso:
  uv run --extra embeddings python -m graphrag_bulas.ingestao [--recriar]

Idempotente: só UNWIND + MERGE, em lotes. Aplica cypher/schema.cypher e cypher/seed.cypher,
carrega Bula/Secao/Chunk das bulas de extracoes.jsonl, CONTEM de extracao.COMPOSICAO, nós e
relações de grafo.jsonl, MENCIONA e embeddings. Acrescenta a parte da carga em
logs/relatorio_e4.md. Spec: docs/superpowers/specs/2026-11-01-e4-resolucao-ingestao-design.md
"""

import json
import re
from collections import defaultdict
from datetime import datetime

from graphrag_bulas.chunks import bula_id, slug
from graphrag_bulas.extracao import COMPOSICAO
from graphrag_bulas.resolucao import RAIZ, SAIDA

CYPHER = RAIZ / "cypher"
MANIFESTO = RAIZ / "data" / "raw" / "manifesto.jsonl"
URL_BULARIO = "https://consultas.anvisa.gov.br/#/bulario/"
LOTE = 500
PROPS = ("frequencia", "gravidade", "efeito", "dose", "confianca", "fonte_chunk_id")


def statements(texto: str) -> list[str]:
    """Comandos de um arquivo .cypher: tira linhas de comentário e corta em ';' no fim da linha.

    ';' no meio de string (textos do seed) não corta, porque vem seguido de espaço.
    """
    sem_comentario = "\n".join(x for x in texto.splitlines() if not x.lstrip().startswith("//"))
    return [s.strip() for s in re.split(r";\s*(?:\n|$)", sem_comentario) if s.strip()]


def lotes(itens, n=LOTE):
    for i in range(0, len(itens), n):
        yield itens[i : i + n]


def ler_grafo(path=SAIDA):
    nos, rels = [], []
    for linha in path.open():
        item = json.loads(linha)
        (nos if item["tipo"] == "no" else rels).append(item)
    return nos, rels


def linhas_bulas(manifesto, bulas, dic_fabricante):
    """Uma linha por bula do escopo, com o Medicamento e o Fabricante do manifesto."""
    rows = []
    for m in manifesto:
        b = bula_id(m["arquivo"])
        if b not in bulas:
            continue
        fab = slug(m["empresa"])
        rows.append(
            {
                "bula": b,
                "med": b.removeprefix("bula_"),
                "nome": m["medicamento"].title(),
                "arquivo": f"data/raw/{m['arquivo']}",
                "registro": m["registro_ms"],
                "data": datetime.strptime(m["data_publicacao"], "%d/%m/%Y").date().isoformat(),
                "fab": dic_fabricante.get(fab, fab),
                "fab_nome": m["empresa"],
            }
        )
    return rows


def linhas_chunks(chunks, bulas):
    return [
        {
            "bula": c["bula"],
            "secao": c["secao"],
            "tipo": c["tipo"],
            "id": c["id"],
            "ordem": c["ordem"],
            "texto": c["texto"],
        }
        for c in chunks
        if c["bula"] in bulas
    ]


def linhas_composicao(nos):
    nomes = {n["id"]: n["nome"] for n in nos if n["label"] == "PrincipioAtivo"}
    return [
        {"med": med, "pa": pa, "nome": nomes.get(pa, pa.replace("_", " ").capitalize())}
        for med, pas in COMPOSICAO.items()
        for pa in pas
    ]


def linhas_menciona(rels):
    """(label, id, chunk) sem repetição: cada chunk menciona as pontas do que sustenta."""
    vistos = set()
    for r in rels:
        for c in r["chunks"]:
            vistos.add((r["label_origem"], r["origem"], c))
            vistos.add((r["label_destino"], r["destino"], c))
    por_label = defaultdict(list)
    for label, i, c in sorted(vistos):
        por_label[label].append({"id": i, "chunk": c})
    return por_label
