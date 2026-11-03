"""Geração da resposta (E5.6). LLM falso, sem Neo4j."""

import pytest

from graphrag_bulas.geracao import NOTA_SEM_CONSULTA, RECUSA, Resposta, gerar_resposta

CTX = {
    "texto": "Fatos do grafo:\n- Marevan -[CONTEM]-> Varfarina [c1] (ids: marevan, varfarina)",
    "chunk_ids": {"c1", "c2"},
    "nos": {"marevan", "varfarina"},
    "trechos": [],
    "sem_consulta": False,
}
VAZIO = {**CTX, "texto": "", "chunk_ids": set(), "nos": set()}


class LLMFalso:
    """Uma fila de respostas por schema (str do nome da classe); Exception é levantada."""

    def __init__(self, **filas):
        self.filas = {k: list(v) for k, v in filas.items()}
        self.prompts = []
        self._schema = None

    def with_structured_output(self, schema):
        self._schema = schema.__name__
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        r = self.filas[self._schema].pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def resp(chunks=("c1",), nos=("marevan",), suporte="total", resposta="Sim."):
    return Resposta(resposta=resposta, chunks=list(chunks), nos=list(nos), suporte=suporte)


def test_resposta_feliz():
    llm = LLMFalso(Resposta=[resp()])
    g = gerar_resposta(llm, "Marevan tem varfarina?", CTX)
    assert g == {
        "resposta": "Sim.",
        "chunks": ["c1"],
        "nos": ["marevan"],
        "confianca": 1.0,
        "recusou": False,
    }
    assert CTX["texto"] in llm.prompts[0] and "Marevan tem varfarina?" in llm.prompts[0]
    assert NOTA_SEM_CONSULTA not in llm.prompts[0]


def test_citacao_inventada_descartada_e_confianca_reduzida():
    llm = LLMFalso(
        Resposta=[resp(chunks=["c1", "inventado"], nos=["marevan", "x"], suporte="parcial")]
    )
    g = gerar_resposta(llm, "p", CTX)
    assert g["chunks"] == ["c1"] and g["nos"] == ["marevan"]
    assert g["confianca"] == 0.3  # 0.6 * 2/4


@pytest.mark.parametrize(
    "r", [resp(suporte="nenhum"), resp(chunks=["inventado"], nos=[]), resp(chunks=[], nos=["x"])]
)
def test_recusa_sem_suporte_ou_sem_citacao_valida(r):
    g = gerar_resposta(LLMFalso(Resposta=[r]), "p", CTX)
    assert g == {"resposta": RECUSA, "chunks": [], "nos": [], "confianca": 0.0, "recusou": True}


def test_contexto_vazio_recusa_sem_chamar_llm():
    llm = LLMFalso(Resposta=[])
    assert gerar_resposta(llm, "p", VAZIO)["recusou"] is True
    assert llm.prompts == []


def test_nota_sem_consulta_no_prompt():
    llm = LLMFalso(Resposta=[resp()])
    gerar_resposta(llm, "p", {**CTX, "sem_consulta": True})
    assert NOTA_SEM_CONSULTA in llm.prompts[0]


def test_falha_do_llm_propaga():
    with pytest.raises(RuntimeError, match="cota"):
        gerar_resposta(LLMFalso(Resposta=[RuntimeError("cota")]), "p", CTX)


def test_contexto_sem_nos_nao_penaliza_nos_citados():
    llm = LLMFalso(Resposta=[resp(chunks=["c1"], nos=["marevan", "x"])])
    g = gerar_resposta(llm, "p", {**CTX, "nos": set()})
    assert g["confianca"] == 1.0 and g["nos"] == []


def test_chunk_id_citado_com_colchetes_vale():
    llm = LLMFalso(Resposta=[resp(chunks=["[c1]", " c1 "], nos=["[marevan]"])])
    g = gerar_resposta(llm, "p", CTX)
    assert not g["recusou"] and g["chunks"] == ["c1"] and g["nos"] == ["marevan"]
    assert g["confianca"] == 1.0


def test_linha_do_contexto_citada_inteira_vale_pelo_id_entre_colchetes():
    linha = "Marevan -[CONTEM]-> Varfarina [c1] (ids: marevan, varfarina)"
    llm = LLMFalso(Resposta=[resp(chunks=[linha])])
    g = gerar_resposta(llm, "p", CTX)
    assert not g["recusou"] and g["chunks"] == ["c1"]


@pytest.mark.parametrize(
    "texto,recusa",
    [
        ("Não há informações específicas sobre a interação no contexto fornecido. Procure um "
         "médico.", True),
        ("O Roacutan não está mencionado no contexto fornecido, portanto não sei.", True),
        ("Não, o contexto mostra que o Cozaar não interage com o Advil.", False),
        ("Não há interação descrita entre os dois. Procure um médico.", False),
    ],
)
def test_resposta_que_diz_que_o_contexto_nao_informa_vira_recusa(texto, recusa):
    g = gerar_resposta(LLMFalso(Resposta=[resp(resposta=texto)]), "p", CTX)
    assert g["recusou"] is recusa


def test_schema_poe_suporte_antes_das_listas_e_limita_tamanho():
    s = Resposta.model_json_schema()
    assert list(s["properties"]) == ["resposta", "suporte", "chunks", "nos"]
    assert s["properties"]["chunks"]["maxItems"] == 8 and s["properties"]["nos"]["maxItems"] == 12


def test_so_nos_validos_sem_chunk_sustentam_a_resposta():
    g = gerar_resposta(LLMFalso(Resposta=[resp(chunks=["Fato sem fonte"], nos=["marevan"])]),
                       "p", CTX)
    assert not g["recusou"] and g["chunks"] == [] and g["nos"] == ["marevan"]
