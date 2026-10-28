"""Modo rag (E5.8): RAG tradicional, top-k chunks por similaridade, sem grafo.

Spec: docs/superpowers/specs/2026-10-28-e5-gds-modo-rag-design.md
"""

import re

from graphrag_bulas.embeddings import embed
from graphrag_bulas.retrieval import buscar_chunks


def recuperar_vetorial(driver, pergunta, k=5):
    """Mesmo formato de recuperar(), com subgrafo vazio e sem Cypher."""
    trechos = buscar_chunks(driver, embed([pergunta])[0], k) if re.search(r"\w", pergunta) else []
    return {"seeds": [], "subgrafo": {"nos": [], "arestas": []}, "trechos": trechos, "cypher": None}
