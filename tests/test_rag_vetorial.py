"""Modo rag (E5.8): top-k chunks sem grafo. Pula sem Neo4j (fixture db em conftest.py)."""

from graphrag_bulas import rag_vetorial
from graphrag_bulas.rag_vetorial import recuperar_vetorial


def test_top_k_por_score_sem_grafo(db):
    r = recuperar_vetorial(db, "Posso tomar Marevan com Advil?", k=3)
    assert r["subgrafo"] == {"nos": [], "arestas": []} and r["cypher"] is None
    scores = [t["score"] for t in r["trechos"]]
    assert len(scores) == 3 and scores == sorted(scores, reverse=True)
    assert all(t["fonte"].startswith("bula_") for t in r["trechos"])


def test_pergunta_sem_palavras_nao_chama_embed(monkeypatch):
    def falha(_):
        raise AssertionError("embed chamado")

    monkeypatch.setattr(rag_vetorial, "embed", falha)
    assert recuperar_vetorial(None, "?!")["trechos"] == []
