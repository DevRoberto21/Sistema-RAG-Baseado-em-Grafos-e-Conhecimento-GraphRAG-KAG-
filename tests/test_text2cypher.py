"""Text-to-Cypher (E5.3). LLM falso: determinístico e sem cota. Neo4j via fixture db."""

import os

import pytest

from graphrag_bulas.text2cypher import (
    IDS_EXEMPLOS,
    SEM_CONSULTA,
    Consulta,
    CypherInvalido,
    _sem_embedding,
    consultar,
    gerar_cypher,
    validar_cypher,
)

MAREVAN_ADVIL = "Posso tomar Marevan com Advil?"
SEEDS = [{"id": "marevan", "nome": "Marevan", "labels": ["Medicamento"]}]
RUIM = "MATCH (n RETURN n"
COZAAR = (
    "MATCH (m:Medicamento {id: 'cozaar'})-[r:CONTEM]->(p:PrincipioAtivo) "
    "RETURN p.nome AS principio_ativo, r.fonte_chunk_id AS fonte_chunk_id LIMIT 50"
)


class LLMFalso:
    """Devolve as respostas em ordem (str vira Consulta; Exception é levantada) e guarda prompts."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.prompts = []

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return Consulta(cypher=r)


def test_prompt_tem_seeds_e_pergunta():
    llm = LLMFalso("  MATCH (n) RETURN n.id LIMIT 1  ")
    assert gerar_cypher(llm, MAREVAN_ADVIL, SEEDS) == "MATCH (n) RETURN n.id LIMIT 1"
    assert "marevan (Medicamento): Marevan" in llm.prompts[0]
    assert MAREVAN_ADVIL in llm.prompts[0]
    assert "Erro:" not in llm.prompts[0]


def test_prompt_da_nova_tentativa_tem_cypher_anterior_e_erro():
    llm = LLMFalso("x")
    gerar_cypher(llm, MAREVAN_ADVIL, [], anterior=RUIM, erro="Invalid input 'RETURN'")
    assert "Seeds:\nnenhuma" in llm.prompts[0]
    assert RUIM in llm.prompts[0]
    assert "Invalid input 'RETURN'" in llm.prompts[0]


def test_exemplos_do_prompt_estao_fora_do_grafo(db):
    # Se o corpus (M2) trouxer um desses remédios, troque o exemplo: ele vazaria a resposta.
    q = "MATCH (n:Entidade) WHERE n.id IN $ids RETURN count(n) AS n"
    assert db.execute_query(q, ids=IDS_EXEMPLOS).records[0]["n"] == 0


@pytest.mark.parametrize(
    "cypher",
    [
        "CALL apoc.load.json('http://x') YIELD value RETURN value",
        "create (n)",
        "MATCH (n) MERGE (m)",
        "LOAD CSV FROM 'file:///x' AS l RETURN l",
        "MATCH (n) DETACH DELETE n",
        # limite documentado na spec: palavra proibida em string também é rejeitada
        "MATCH (n) WHERE n.nome = 'set' RETURN n",
    ],
)
def test_palavra_proibida_rejeitada_sem_tocar_no_neo4j(cypher):
    with pytest.raises(CypherInvalido, match="palavra proibida"):
        validar_cypher(None, cypher)  # driver None: a regex roda antes do EXPLAIN


def test_cypher_vazio_e_sem_consulta():
    with pytest.raises(CypherInvalido, match=SEM_CONSULTA):
        validar_cypher(None, "   ")


def test_sem_embedding_remove_vetores_aninhados():
    linha = {"m": {"nome": "a", "embedding_nome": [1.0]}, "l": [{"embedding": [2.0], "id": "x"}]}
    assert _sem_embedding(linha) == {"m": {"nome": "a"}, "l": [{"id": "x"}]}


def test_validar_aceita_leitura(db):
    validar_cypher(db, COZAAR)


def test_validar_rejeita_sintaxe_com_mensagem_do_neo4j(db):
    with pytest.raises(CypherInvalido, match="Invalid input"):
        validar_cypher(db, RUIM)


def contagem(db):
    q = "MATCH (n) WITH count(n) AS n MATCH ()-[r]->() RETURN n, count(r) AS r"
    return dict(db.execute_query(q).records[0])


def test_consultar_devolve_linhas(db):
    r = consultar(db, LLMFalso(COZAAR), "x", SEEDS)
    assert r == {
        "query": COZAAR,
        "linhas": [{"principio_ativo": "Losartana", "fonte_chunk_id": None}],
        "erro": None,
    }


def test_consultar_tenta_de_novo_com_o_erro(db):
    llm = LLMFalso(RUIM, COZAAR)
    r = consultar(db, llm, "x", SEEDS)
    assert r["erro"] is None and r["linhas"]
    assert RUIM in llm.prompts[1] and "Invalid input" in llm.prompts[1]


def test_consultar_desiste_apos_duas_falhas(db):
    r = consultar(db, LLMFalso(RUIM, RUIM), "x", SEEDS)
    assert r["query"] == RUIM and r["linhas"] == []
    assert "Invalid input" in r["erro"]


def test_consultar_vazio_nao_tenta_de_novo(db):
    llm = LLMFalso("")
    assert consultar(db, llm, "x", SEEDS) == {"query": None, "linhas": [], "erro": SEM_CONSULTA}
    assert len(llm.prompts) == 1


def test_consultar_bloqueia_escrita(db):
    antes = contagem(db)
    r = consultar(db, LLMFalso("CREATE (:X)", "CREATE (:X)"), "x", SEEDS)
    assert "palavra proibida" in r["erro"]
    assert contagem(db) == antes


def test_consultar_sobrevive_a_falha_do_llm(db):
    r = consultar(db, LLMFalso(RuntimeError("cota")), "x", SEEDS)
    assert r == {"query": None, "linhas": [], "erro": "llm: cota"}


@pytest.mark.skipif(
    os.getenv("GRAPHRAG_TESTAR_LLM") != "1",
    reason="Gemini real: defina GRAPHRAG_TESTAR_LLM=1 (gasta cota, não determinístico)",
)
def test_gemini_real_gera_cypher_com_fonte(db):
    from graphrag_bulas.config import get_llm
    from graphrag_bulas.retrieval import buscar_seeds

    seeds = buscar_seeds(db, MAREVAN_ADVIL)["entidades"]
    r = consultar(db, get_llm(temperature=0), MAREVAN_ADVIL, seeds)
    assert r["erro"] is None, r
    assert any(linha.get("fonte_chunk_id") for linha in r["linhas"]), r
