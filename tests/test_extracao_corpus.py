"""Extração no corpus (E3.4). LLM falso, cache em diretório temporário."""

import pytest

from graphrag_bulas import extracao_corpus as ec
from graphrag_bulas.modelos import Extracao

BOA = Extracao.model_validate({
    "entidades": [{"id": "cozaar", "label": "Medicamento", "nome": "Cozaar"},
                  {"id": "tontura", "label": "EfeitoAdverso", "nome": "Tontura"},
                  {"id": "x", "label": "Populacao", "nome": "X"}],
    "relacoes": [{"tipo": "PODE_CAUSAR", "origem": "cozaar", "destino": "tontura",
                  "frequencia": "comum", "confianca": 1.0}],
})


def chunk(i, texto="Tontura: comum."):
    return {"id": f"bula_cozaar_reacoes_adversas_{i}", "bula": "bula_cozaar",
            "tipo": "reacoes_adversas", "texto": texto}


class LLMFalso:
    def __init__(self, *respostas):
        self.respostas, self.chamadas = list(respostas), 0

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        self.chamadas += 1
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture(autouse=True)
def cache_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "CACHE", tmp_path)


def rodar(chunks, llm, **kw):
    return ec.rodar(chunks, llm, "modelo", dormir=lambda s: None, **kw)


def test_valida_e_usa_cache_na_segunda_rodada():
    linhas, conta = rodar([chunk(0)], LLMFalso(BOA))
    assert conta == {"cache": 0, "chamadas": 1, "falhas": 0, "sem_cota": 0}
    assert linhas[0]["chunk_id"] == "bula_cozaar_reacoes_adversas_0"
    assert len(linhas[0]["relacoes"]) == 1 and "Populacao" in linhas[0]["descartes"][0]

    llm = LLMFalso()
    linhas2, conta = rodar([chunk(0)], llm)
    assert llm.chamadas == 0 and conta["cache"] == 1 and linhas2 == linhas


def test_prompt_ou_modelo_novo_invalida_cache():
    a = ec.caminho_cache(chunk(0), "m1")
    assert a != ec.caminho_cache(chunk(0, "Cefaleia: rara."), "m1")
    assert a != ec.caminho_cache(chunk(0), "m2")


def test_retry_recupera_de_falha_passageira():
    llm = LLMFalso(RuntimeError("503"), BOA)
    linhas, conta = rodar([chunk(0)], llm)
    assert llm.chamadas == 2 and conta["falhas"] == 0 and linhas


def test_falha_persistente_pula_chunk_sem_gravar_cache(tmp_path):
    erros = [RuntimeError("503")] * (len(ec.ESPERAS_S) + 1)
    linhas, conta = rodar([chunk(0), chunk(1)], LLMFalso(*erros, BOA))
    assert conta["falhas"] == 1 and [x["chunk_id"][-1] for x in linhas] == ["1"]
    assert len(list(tmp_path.iterdir())) == 1


def test_teto_de_chamadas():
    llm = LLMFalso(BOA)
    linhas, conta = rodar([chunk(0), chunk(1), chunk(2)], llm, max_chamadas=1)
    assert llm.chamadas == 1 and conta["sem_cota"] == 2 and len(linhas) == 1


def test_cota_diaria_para_a_rodada_sem_retry():
    cota = RuntimeError("429 RESOURCE_EXHAUSTED ... GenerateRequestsPerDayPerProjectPerModel")
    llm = LLMFalso(BOA, cota)
    linhas, conta = rodar([chunk(0), chunk(1), chunk(2)], llm)
    assert llm.chamadas == 2 and len(linhas) == 1
    assert conta["sem_cota"] == 2 and conta["falhas"] == 0
