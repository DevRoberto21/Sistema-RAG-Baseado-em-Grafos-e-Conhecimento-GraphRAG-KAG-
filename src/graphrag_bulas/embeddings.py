"""Embeddings locais (sentence-transformers) gravados no Neo4j.

Uso: uv run python -m graphrag_bulas.embeddings
"""

from graphrag_bulas.config import EMBEDDING_MODEL, get_driver

# (label, propriedade de texto, propriedade do embedding) — ver docs/modelagem.md, seção 5.
ALVOS = [("Entidade", "nome", "embedding_nome"), ("Chunk", "texto", "embedding")]

_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed(textos):
    """Vetores normalizados (cosseno = produto interno)."""
    return get_model().encode(textos, normalize_embeddings=True).tolist()


def embed_missing(driver, batch_size=64):
    """Grava embedding nos nós que ainda não têm. Retorna quantos nós gravou por label."""
    gravados = {}
    for label, src, dst in ALVOS:
        gravados[label] = 0
        while True:
            rows = driver.execute_query(
                f"MATCH (n:{label}) WHERE n.{dst} IS NULL AND n.{src} IS NOT NULL "
                f"RETURN n.id AS id, n.{src} AS texto LIMIT $k",
                k=batch_size,
            ).records
            if not rows:
                break
            vetores = embed([r["texto"] for r in rows])
            driver.execute_query(
                f"UNWIND $rows AS r MATCH (n:{label} {{id: r.id}}) "
                f"CALL db.create.setNodeVectorProperty(n, '{dst}', r.v)",
                rows=[{"id": r["id"], "v": v} for r, v in zip(rows, vetores, strict=True)],
            )
            gravados[label] += len(rows)
    return gravados


if __name__ == "__main__":
    with get_driver() as driver:
        print(embed_missing(driver))
