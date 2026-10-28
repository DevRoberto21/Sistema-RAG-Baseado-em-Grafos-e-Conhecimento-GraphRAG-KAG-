"""Retrieval E5.1 + E5.2 sobre o grafo semente. Pula sem Neo4j (fixture db em conftest.py)."""

from graphrag_bulas.retrieval import buscar_seeds, termos_fulltext

MAREVAN_ADVIL = "Posso tomar Marevan com Advil?"


def ids_seeds(db, pergunta):
    return {s["id"] for s in buscar_seeds(db, pergunta)["entidades"]}


def test_termos_fulltext_ignora_palavras_curtas_e_especiais():
    assert (
        termos_fulltext('Posso tomar "Marevan" (com) Advil? AND/OR:') == "Posso tomar Marevan Advil"
    )


def test_seeds_marevan_advil_sem_ruido_vetorial(db):
    seeds = ids_seeds(db, MAREVAN_ADVIL)
    assert {"marevan", "advil"} <= seeds
    assert "enalapril" not in seeds  # vetor 0.70, abaixo do corte


def test_seed_aine_vem_do_fulltext(db):
    ents = {s["id"]: s for s in buscar_seeds(db, "Varfarina interage com algum AINE?")["entidades"]}
    assert "varfarina" in ents
    assert "fulltext" in ents["aine"]["fontes"]


def test_seeds_gravidez(db):
    seeds = ids_seeds(db, "Quais anti-hipertensivos são contraindicados na gravidez?")
    assert {"anti_hipertensivo", "gestante"} <= seeds


def test_chunks_seed_ordenados_e_com_fonte(db):
    chunks = buscar_seeds(db, MAREVAN_ADVIL, k_chunks=3)["chunks"]
    assert len(chunks) == 3
    assert [c["score"] for c in chunks] == sorted((c["score"] for c in chunks), reverse=True)
    assert all(c["fonte"].startswith("bula_") for c in chunks)


def test_pergunta_sem_palavras_nao_consulta(db):
    assert buscar_seeds(db, " ?! ") == {"entidades": [], "chunks": []}


def test_caracteres_especiais_do_lucene_nao_quebram(db):
    seeds = ids_seeds(db, 'Marevan "AND" (Advil) : / ~ * [AINE]?')
    assert {"marevan", "advil"} <= seeds
