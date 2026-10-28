"""Text-to-Cypher (E5.3). LLM falso: determinístico e sem cota. Neo4j via fixture db."""

from graphrag_bulas.text2cypher import IDS_EXEMPLOS, Consulta, gerar_cypher

MAREVAN_ADVIL = "Posso tomar Marevan com Advil?"
SEEDS = [{"id": "marevan", "nome": "Marevan", "labels": ["Medicamento"]}]
RUIM = "MATCH (n RETURN n"


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
