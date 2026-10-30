import json

import pytest

from graphrag_bulas.gold import GOLD, erros


def _doc(entidades, relacoes):
    return {"chunks": [{"id": "c0", "entidades": entidades, "relacoes": relacoes}]}


COZAAR = {"id": "cozaar", "label": "Medicamento", "nome": "Cozaar"}


def test_anotacao_valida():
    doc = _doc(
        [COZAAR, {"id": "tontura", "label": "EfeitoAdverso", "nome": "Tontura"}],
        [{"tipo": "PODE_CAUSAR", "origem": "cozaar", "destino": "tontura",
          "props": {"frequencia": "comum"}}],
    )
    assert erros(doc) == []


@pytest.mark.parametrize("entidades,relacoes,trecho", [
    ([{"id": "x", "label": "Doenca"}], [], "label inválido"),
    ([{"id": "Tontura", "label": "EfeitoAdverso"}], [], "slug"),
    ([{"id": "crianca", "label": "Populacao"}], [], "Populacao"),
    ([COZAAR], [{"tipo": "CAUSA", "origem": "cozaar", "destino": "x"}], "relação inválida"),
    ([COZAAR], [{"tipo": "PODE_CAUSAR", "origem": "cozaar", "destino": "tontura"}],
     "não está em entidades"),
    ([COZAAR, {"id": "hipertensao", "label": "Condicao"}],
     [{"tipo": "PODE_CAUSAR", "origem": "cozaar", "destino": "hipertensao"}], "esperado"),
    ([COZAAR, {"id": "tontura", "label": "EfeitoAdverso"}],
     [{"tipo": "PODE_CAUSAR", "origem": "cozaar", "destino": "tontura",
       "props": {"frequencia": "frequente"}}], "fora de"),
])
def test_anotacao_invalida(entidades, relacoes, trecho):
    probs = erros(_doc(entidades, relacoes))
    assert any(trecho in p for p in probs), probs


@pytest.mark.parametrize("arq", sorted(GOLD.glob("bula_*.json")), ids=lambda p: p.name)
def test_gold_versionado_valido(arq):
    assert erros(json.loads(arq.read_text())) == []
