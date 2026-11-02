import json

from graphrag_bulas.avaliacao import (
    cobertura,
    metricas,
    relatorio,
    responder_llm_puro,
    rodar,
    validar_gold,
)
from graphrag_bulas.geracao import Resposta

P1 = {"id": "q1", "tipo": "1hop", "fatos": [["tontura"], ["hemorragia", "sangramento"]],
      "fontes": ["c1"]}
PS = {"id": "q2", "tipo": "sem_resposta", "fatos": [], "fontes": []}


def linha(**kw):
    return {"resposta": "", "recusou": False, "citados": [], "erro": None, **kw}


def test_cobertura_ignora_acento_maiuscula_e_aceita_variante():
    assert cobertura("Pode causar TONTURA e Sangramento.", P1["fatos"]) == 1.0
    assert cobertura("Pode causar tontura.", P1["fatos"]) == 0.5


def test_metricas_pergunta_com_resposta():
    m = metricas(P1, linha(resposta="tontura", citados=["c1", "c9"]))
    assert m == {"cobertura": 0.5, "acerto": 0, "recusa_falsa": 0, "fidelidade": 0.5}


def test_metricas_recusa_zera_cobertura_e_fidelidade_indefinida():
    m = metricas(P1, linha(resposta="tontura sangramento", recusou=True))
    assert m == {"cobertura": 0.0, "acerto": 0, "recusa_falsa": 1, "fidelidade": None}


def test_metricas_sem_resposta():
    assert metricas(PS, linha(recusou=True)) == {"recusa_correta": 1, "alucinacao": 0}
    assert metricas(PS, linha()) == {"recusa_correta": 0, "alucinacao": 1}


def test_metricas_linha_com_erro_e_none():
    assert metricas(P1, linha(erro="boom")) is None


def test_validar_gold():
    perguntas = ([{**P1, "id": f"a{i}"} for i in range(15)]
                 + [{**P1, "id": f"b{i}", "tipo": "multihop"} for i in range(15)]
                 + [{**PS, "id": f"c{i}"} for i in range(10)])
    assert validar_gold({"perguntas": perguntas}, {"c1"}) == []
    erros = validar_gold({"perguntas": perguntas}, set())
    assert any("c1" in e for e in erros)
    erros = validar_gold({"perguntas": perguntas[:-1] + [perguntas[0]]}, {"c1"})
    assert any("repetido" in e for e in erros) and any("sem_resposta" in e for e in erros)



class LLMFalso:
    def __init__(self, r):
        self.r = r

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        return self.r


def test_llm_puro_recusa_com_suporte_nenhum():
    r = Resposta(resposta="Não sei.", chunks=[], nos=[], suporte="nenhum")
    assert responder_llm_puro(LLMFalso(r), "x")["recusou"] is True
    r = Resposta(resposta="Sim.", chunks=[], nos=[], suporte="total")
    out = responder_llm_puro(LLMFalso(r), "x")
    assert out["recusou"] is False and out["trechos"] == []


def test_rodar_grava_retoma_e_registra_erro(tmp_path):
    saida = tmp_path / "r.jsonl"
    chamadas = []

    def resp(pergunta, modo):
        chamadas.append((pergunta, modo))
        if pergunta == "ruim":
            raise RuntimeError("boom")
        return {"resposta": "tontura", "recusou": False, "confianca": 0.9,
                "trechos": [{"chunk_id": "c1", "citado": True},
                            {"chunk_id": "c2", "citado": False}]}

    ps = [{"id": "q1", "pergunta": "boa"}, {"id": "q2", "pergunta": "ruim"}]
    assert rodar(ps, ["rag"], resp, saida) == 2
    linhas = [json.loads(x) for x in saida.read_text().splitlines()]
    assert linhas[0]["citados"] == ["c1"] and linhas[1]["erro"] == "RuntimeError: boom"
    chamadas.clear()
    rodar(ps, ["rag"], resp, saida)
    assert chamadas == [("ruim", "rag")]


def test_relatorio_tem_tabelas_e_aviso():
    ps = [P1, PS]
    linhas = [{"id": "q1", "modo": "rag", "segundos": 2.0, **linha(resposta="tontura sangramento",
                                                                   citados=["c1"])},
              {"id": "q2", "modo": "rag", "segundos": 1.0, **linha(recusou=True)}]
    md = relatorio(ps, linhas)
    assert "| rag | 1.000 | 1.000 | 1.000 | 0.000 | 1.000 | 0.000 | 1.5 | 0 |" in md
    assert "sem revisão humana" in md