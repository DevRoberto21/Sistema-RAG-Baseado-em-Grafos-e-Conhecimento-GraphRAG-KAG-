"""API responder (E5.7) no grafo semente. LLM falso; Gemini real com GRAPHRAG_TESTAR_LLM=1."""

import os

import pytest
from test_geracao import LLMFalso, resp

from graphrag_bulas.api import responder
from graphrag_bulas.text2cypher import Consulta

MAREVAN_ADVIL = "Posso tomar Marevan com Advil?"
INTERACAO = (
    "MATCH (:Medicamento {id: 'marevan'})-[:CONTEM]->(:PrincipioAtivo)-[r:INTERAGE_COM]-(x) "
    "RETURN x.nome AS com, r.efeito AS efeito, r.fonte_chunk_id AS fonte_chunk_id LIMIT 50"
)
CHAVES = {"modo", "resposta", "subgrafo", "cypher", "nos", "confianca", "recusou", "trechos"}


def test_responder_monta_o_contrato(db):
    llm = LLMFalso(
        Consulta=[Consulta(cypher=INTERACAO)],
        Resposta=[resp(chunks=["bula_marevan_interacoes_0"], nos=["varfarina"])],
    )
    r = responder(MAREVAN_ADVIL, driver=db, llm=llm)
    assert set(r) == CHAVES
    assert r["modo"] == "graphrag" and r["recusou"] is False and r["confianca"] == 1.0
    assert r["cypher"] == INTERACAO
    assert r["nos"] == ["varfarina"] and r["subgrafo"]["arestas"]
    citados = [t["chunk_id"] for t in r["trechos"] if t["citado"]]
    assert citados == ["bula_marevan_interacoes_0"]


def test_responder_sem_cypher_e_com_recusa(db):
    llm = LLMFalso(Consulta=[Consulta(cypher="")], Resposta=[resp(suporte="nenhum")])
    r = responder("Qual a cor do comprimido de Cozaar?", driver=db, llm=llm)
    assert r["cypher"] is None and r["recusou"] is True and r["confianca"] == 0.0
    assert not any(t["citado"] for t in r["trechos"])
    assert "não cobre" in llm.prompts[-1]  # sem_consulta chegou à geração


def test_modo_rag_ainda_nao_existe():
    with pytest.raises(NotImplementedError, match="E5.8"):
        responder("x", modo="rag")


def test_modo_invalido():
    with pytest.raises(ValueError, match="modo desconhecido"):
        responder("x", modo="kag")


@pytest.mark.skipif(
    os.getenv("GRAPHRAG_TESTAR_LLM") != "1",
    reason="Gemini real: defina GRAPHRAG_TESTAR_LLM=1 (gasta cota, não determinístico)",
)
def test_gemini_real_responde_e_recusa(db):
    from graphrag_bulas.config import get_llm

    llm = get_llm(temperature=0)
    ok = responder(MAREVAN_ADVIL, driver=db, llm=llm)
    assert not ok["recusou"] and any(t["citado"] for t in ok["trechos"]), ok
    nao = responder("Qual a cor do comprimido de Cozaar?", driver=db, llm=llm)
    assert nao["recusou"], nao
