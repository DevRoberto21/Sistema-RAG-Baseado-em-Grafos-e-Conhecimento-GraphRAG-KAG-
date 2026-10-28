"""Retrieval E5.1 + E5.2 sobre o grafo semente. Pula sem Neo4j (fixture db em conftest.py)."""

from graphrag_bulas.retrieval import termos_fulltext


def test_termos_fulltext_ignora_palavras_curtas_e_especiais():
    assert (
        termos_fulltext('Posso tomar "Marevan" (com) Advil? AND/OR:') == "Posso tomar Marevan Advil"
    )
