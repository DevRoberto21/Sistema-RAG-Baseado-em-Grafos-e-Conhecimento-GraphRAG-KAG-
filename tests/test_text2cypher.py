"""Text-to-Cypher (E5.3). LLM falso: determinístico e sem cota. Neo4j via fixture db."""

import pytest

from graphrag_bulas.text2cypher import (
    IDS_EXEMPLOS,
    SEM_CONSULTA,
    Consulta,
    CypherInvalido,
    _sem_embedding,
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
