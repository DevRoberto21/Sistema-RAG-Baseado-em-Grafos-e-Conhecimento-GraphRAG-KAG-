"""API única (E5.7, E5.8): responder(pergunta, modo) -> contrato JSON da UI e do E7.

Specs: docs/superpowers/specs/2026-10-28-e5-contexto-geracao-api-design.md
       docs/superpowers/specs/2026-10-28-e5-gds-modo-rag-design.md
"""

from graphrag_bulas.config import get_driver, get_llm
from graphrag_bulas.contexto import montar_contexto
from graphrag_bulas.geracao import gerar_resposta
from graphrag_bulas.rag_vetorial import recuperar_vetorial
from graphrag_bulas.retrieval import recuperar


def responder(pergunta, modo="graphrag", driver=None, llm=None):
    """Pergunta -> resposta citada. "graphrag": grafo + GDS + Cypher; "rag": só vetor (E5.8)."""
    if modo not in ("graphrag", "rag"):
        raise ValueError(f"modo desconhecido: {modo}")
    llm = llm or get_llm(temperature=0)
    if driver is None:
        with get_driver() as d:
            return responder(pergunta, modo, d, llm)
    if modo == "rag":
        r = recuperar_vetorial(driver, pergunta)
    else:
        r = recuperar(driver, pergunta, llm=llm)
    ctx = montar_contexto(r)
    g = gerar_resposta(llm, pergunta, ctx)
    citados = set(g["chunks"])
    return {
        "modo": modo,
        "resposta": g["resposta"],
        "subgrafo": r["subgrafo"],
        "cypher": r["cypher"]["query"] if r["cypher"] else None,
        "nos": g["nos"],
        "confianca": g["confianca"],
        "recusou": g["recusou"],
        "trechos": [{**t, "citado": t["chunk_id"] in citados} for t in ctx["trechos"]],
    }
