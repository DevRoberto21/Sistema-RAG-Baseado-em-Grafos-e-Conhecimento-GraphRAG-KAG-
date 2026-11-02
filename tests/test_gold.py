import json

import pytest

from graphrag_bulas.gold import GOLD, avaliar_docs, erros


def _doc(entidades, relacoes):
    return {"chunks": [{"id": "c0", "entidades": entidades, "relacoes": relacoes}]}


COZAAR = {"id": "cozaar", "label": "Medicamento", "nome": "Cozaar"}


def test_anotacao_valida():
    doc = _doc(
        [COZAAR, {"id": "tontura", "label": "EfeitoAdverso", "nome": "Tontura"}],
        [
            {
                "tipo": "PODE_CAUSAR",
                "origem": "cozaar",
                "destino": "tontura",
                "props": {"frequencia": "comum"},
            }
        ],
    )
    assert erros(doc) == []


@pytest.mark.parametrize(
    "entidades,relacoes,trecho",
    [
        ([{"id": "x", "label": "Doenca"}], [], "label inválido"),
        ([{"id": "Tontura", "label": "EfeitoAdverso"}], [], "slug"),
        ([{"id": "crianca", "label": "Populacao"}], [], "Populacao"),
        ([COZAAR], [{"tipo": "CAUSA", "origem": "cozaar", "destino": "x"}], "relação inválida"),
        (
            [COZAAR],
            [{"tipo": "PODE_CAUSAR", "origem": "cozaar", "destino": "tontura"}],
            "não está em entidades",
        ),
        (
            [COZAAR, {"id": "hipertensao", "label": "Condicao"}],
            [{"tipo": "PODE_CAUSAR", "origem": "cozaar", "destino": "hipertensao"}],
            "esperado",
        ),
        (
            [COZAAR, {"id": "tontura", "label": "EfeitoAdverso"}],
            [
                {
                    "tipo": "PODE_CAUSAR",
                    "origem": "cozaar",
                    "destino": "tontura",
                    "props": {"frequencia": "frequente"},
                }
            ],
            "fora de",
        ),
    ],
)
def test_anotacao_invalida(entidades, relacoes, trecho):
    probs = erros(_doc(entidades, relacoes))
    assert any(trecho in p for p in probs), probs


@pytest.mark.parametrize("arq", sorted(GOLD.glob("bula_*.json")), ids=lambda p: p.name)
def test_gold_versionado_valido(arq):
    assert erros(json.loads(arq.read_text())) == []


def _ent(id_, label):
    return {"id": id_, "label": label, "nome": id_}


def _rel(o, d, tipo="PODE_CAUSAR"):
    return {"tipo": tipo, "origem": o, "destino": d}


def _chunk(cid, ents, rels):
    return {"id": cid, "entidades": ents, "relacoes": rels}


MED, TONT = _ent("cozaar", "Medicamento"), _ent("tontura", "EfeitoAdverso")
GOLD_1 = [
    {
        "bula": "b",
        "anotador": "x",
        "chunks": [_chunk("c0", [MED, TONT], [_rel("cozaar", "tontura")])],
    }
]


def _ext(cid, ents, rels):
    return [{"chunk_id": cid, "bula": "b", "entidades": ents, "relacoes": rels}]


def _rel_cont(m):
    return {k: m["relacoes"][k] for k in ("tp", "fp", "fn")}


def test_avaliar_acerto_exato():
    m = avaliar_docs(GOLD_1, _ext("c0", [MED, TONT], [_rel("cozaar", "tontura")]), False)
    assert _rel_cont(m) == {"tp": 1, "fp": 0, "fn": 0}
    assert m["relacoes"]["f1"] == 1.0 and m["entidades"]["tp"] == 2


def test_avaliar_falso_positivo_e_negativo():
    nausea = _ent("nausea", "EfeitoAdverso")
    m = avaliar_docs(GOLD_1, _ext("c0", [MED, nausea], [_rel("cozaar", "nausea")]), False)
    assert _rel_cont(m) == {"tp": 0, "fp": 1, "fn": 1}
    assert m["por_tipo"]["PODE_CAUSAR"]["fn"] == 1 and m["por_bula"]["b"]["fp"] == 1


def test_avaliar_so_acerta_normalizado():
    g = [
        {
            "bula": "b",
            "anotador": "x",
            "chunks": [
                _chunk(
                    "c0",
                    [MED, _ent("losartana", "PrincipioAtivo")],
                    [_rel("cozaar", "losartana", "TEM_PRINCIPIO_ATIVO")],
                )
            ],
        }
    ]
    e = _ext(
        "c0",
        [MED, _ent("losartana_potassica", "PrincipioAtivo")],
        [_rel("cozaar", "losartana_potassica", "TEM_PRINCIPIO_ATIVO")],
    )
    assert _rel_cont(avaliar_docs(g, e, False)) == {"tp": 0, "fp": 1, "fn": 1}
    assert _rel_cont(avaliar_docs(g, e, True)) == {"tp": 1, "fp": 0, "fn": 0}


def test_avaliar_chunk_sem_extracao_e_chunk_fora_do_gold():
    e = _ext("outro", [MED], [_rel("cozaar", "x")])
    m = avaliar_docs(GOLD_1, e, False)
    assert _rel_cont(m) == {"tp": 0, "fp": 0, "fn": 1}
    assert m["entidades"]["fn"] == 2


def test_avaliar_sem_itens_nao_divide_por_zero():
    m = avaliar_docs([{"bula": "b", "chunks": [_chunk("c0", [], [])]}], [], False)
    assert (m["relacoes"]["precisao"], m["relacoes"]["recall"], m["relacoes"]["f1"]) == (
        0.0,
        0.0,
        0.0,
    )
