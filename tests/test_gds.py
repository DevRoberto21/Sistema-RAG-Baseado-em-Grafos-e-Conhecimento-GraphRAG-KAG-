"""GDS no contexto (E5.4) sobre o grafo semente. Pula sem Neo4j (fixture db em conftest.py)."""

from types import SimpleNamespace

from graphrag_bulas import gds
from graphrag_bulas.gds import ranquear
from graphrag_bulas.retrieval import buscar_seeds, expandir

MAREVAN_ADVIL = "Posso tomar Marevan com Advil?"


def expandido(db, pergunta=MAREVAN_ADVIL):
    return expandir(db, buscar_seeds(db, pergunta))


def projecoes_ctx(db):
    recs = db.execute_query("CALL gds.graph.list() YIELD graphName RETURN graphName").records
    return [x["graphName"] for x in recs if x["graphName"].startswith("ctx_")]


def test_pagerank_comunidade_e_caminho_marevan_advil(db):
    r = expandido(db)
    ranquear(db, r)
    assert r["gds"]["erro"] is None
    nos = r["subgrafo"]["nos"]
    assert all(n["pagerank"] is not None and n["comunidade"] is not None for n in nos)
    top3 = [n["id"] for n in sorted(nos, key=lambda n: -n["pagerank"])[:3]]
    assert "marevan" in top3
    caminho = next(c for c in r["gds"]["caminhos"] if {c[0], c[-1]} == {"marevan", "advil"})
    assert len(caminho) >= 3
    assert projecoes_ctx(db) == []


def test_subgrafo_vazio_nao_chama_gds():
    r = {"seeds": [], "subgrafo": {"nos": [], "arestas": []}, "trechos": []}
    ranquear(None, r)  # driver None: qualquer chamada ao Neo4j quebraria
    assert r["gds"] == {"caminhos": [], "erro": None}


def test_erro_do_gds_nao_levanta_e_apaga_projecao(db, monkeypatch):
    db.execute_query(
        "CALL gds.graph.project('ctx_fixo', 'Entidade', '*') YIELD graphName RETURN graphName"
    )
    monkeypatch.setattr(gds, "uuid4", lambda: SimpleNamespace(hex="fixo"))
    r = expandido(db)
    ranquear(db, r)  # projeção 'ctx_fixo' já existe: o GDS levanta
    assert r["gds"]["erro"] and r["gds"]["caminhos"] == []
    assert all(n["pagerank"] is None for n in r["subgrafo"]["nos"])
    assert projecoes_ctx(db) == []
