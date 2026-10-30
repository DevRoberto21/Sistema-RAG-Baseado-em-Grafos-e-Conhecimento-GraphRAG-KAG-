import pytest
from pydantic import ValidationError

from graphrag_bulas.modelos import Extracao


def test_extracao_valida():
    e = Extracao.model_validate({
        "entidades": [
            {"id": "cozaar", "label": "Medicamento", "nome": "Cozaar"},
            {"id": "tontura", "label": "EfeitoAdverso", "nome": "Tontura"},
        ],
        "relacoes": [{"tipo": "PODE_CAUSAR", "origem": "cozaar", "destino": "tontura",
                      "frequencia": "comum", "confianca": 0.9}],
    })
    assert e.relacoes[0].gravidade is None


@pytest.mark.parametrize("rel", [
    {"tipo": "CAUSA", "origem": "a", "destino": "b", "confianca": 1},
    {"tipo": "PODE_CAUSAR", "origem": "a", "destino": "b", "confianca": 1.5},
    {"tipo": "PODE_CAUSAR", "origem": "a", "destino": "b", "frequencia": "frequente",
     "confianca": 1},
])
def test_relacao_fora_do_schema(rel):
    with pytest.raises(ValidationError):
        Extracao.model_validate({"entidades": [], "relacoes": [rel]})


def test_json_schema_para_saida_estruturada():
    s = Extracao.model_json_schema()
    assert {"Entidade", "Relacao"} <= set(s["$defs"])
