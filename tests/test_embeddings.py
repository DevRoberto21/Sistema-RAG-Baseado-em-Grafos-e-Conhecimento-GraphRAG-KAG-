"""embed_missing no grafo semente. Pulado sem sentence-transformers ou sem Neo4j."""

import pytest

pytest.importorskip("sentence_transformers")

from graphrag_bulas.embeddings import embed, embed_missing


def test_embed_missing_cobre_tudo_e_busca_vetorial(db):
    embed_missing(db)
    faltando = db.execute_query(
        "MATCH (n) WHERE (n:Entidade AND n.embedding_nome IS NULL) "
        "OR (n:Chunk AND n.embedding IS NULL) RETURN count(n) AS n"
    ).records[0]["n"]
    assert faltando == 0
    assert embed_missing(db) == {"Entidade": 0, "Chunk": 0}  # idempotente

    rows = db.execute_query(
        "CALL db.index.vector.queryNodes('chunk_embedding', 3, $v) YIELD node RETURN node.id AS id",
        v=embed(["risco de sangramento com anticoagulante e anti-inflamatório"])[0],
    ).records
    assert any("interacoes" in r["id"] for r in rows)
