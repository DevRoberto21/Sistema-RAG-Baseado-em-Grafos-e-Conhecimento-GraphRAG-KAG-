"""Extração por LLM (E3.2). LLM falso: determinístico e sem cota."""

import json
import os
from pathlib import Path

import pytest

from graphrag_bulas.chunks import TIPOS
from graphrag_bulas.extracao import EXEMPLOS, FOCO, extrair, montar_prompt, validar
from graphrag_bulas.modelos import RELACOES, Extracao

GOLD = Path(__file__).resolve().parents[1] / "data" / "gold"
CHUNK = {"id": "bula_cozaar_reacoes_adversas_0", "bula": "bula_cozaar",
         "tipo": "reacoes_adversas", "texto": "Tontura: comum."}


class LLMFalso:
    def __init__(self, resposta):
        self.resposta, self.prompts, self.schema = resposta, [], None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.resposta


def test_prompt_tem_medicamento_foco_e_trecho():
    p = montar_prompt(CHUNK)
    trecho = p.split("Exemplos:")[1].rsplit("Medicamento da bula:", 1)[1]
    assert trecho.startswith(" cozaar\nSeção: reacoes_adversas")
    assert FOCO["reacoes_adversas"] in trecho and "Tontura: comum." in trecho


def test_extrair_usa_schema_extracao():
    vazio = Extracao(entidades=[], relacoes=[])
    llm = LLMFalso(vazio)
    assert extrair(llm, CHUNK) is vazio
    assert llm.schema is Extracao and len(llm.prompts) == 1


def test_foco_cobre_toda_secao():
    assert set(FOCO) == set(TIPOS.values())


def test_exemplos_respeitam_o_schema_e_ficam_fora_do_gold():
    gold = {p.stem.removeprefix("bula_") for p in GOLD.glob("bula_*.json")}
    for med, tipo, _, saida in EXEMPLOS:
        assert med not in gold and tipo in FOCO
        labels = {e.id: e.label for e in saida.entidades}
        for r in saida.relacoes:
            origens, destinos = RELACOES[r.tipo]
            assert labels[r.origem] in origens and labels[r.destino] in destinos


@pytest.mark.skipif(
    os.getenv("GRAPHRAG_TESTAR_LLM") != "1",
    reason="Gemini real: defina GRAPHRAG_TESTAR_LLM=1 (gasta cota, não determinístico)",
)
def test_gemini_real_extrai_reacoes_do_cozaar():
    from graphrag_bulas.config import get_llm

    chunks = json.loads((GOLD / "bula_cozaar.json").read_text())["chunks"]
    chunk = next(c for c in chunks if c["tipo"] == "reacoes_adversas")
    e = extrair(get_llm(temperature=0), {**chunk, "bula": "bula_cozaar"})
    assert any(r.tipo == "PODE_CAUSAR" and r.origem == "cozaar" for r in e.relacoes), e


def _ext(entidades, relacoes):
    return Extracao.model_validate({"entidades": entidades, "relacoes": relacoes})


COZAAR = {"id": "cozaar", "label": "Medicamento", "nome": "Cozaar"}
TONTURA = {"id": "tontura", "label": "EfeitoAdverso", "nome": "Tontura"}


def rel(tipo, origem, destino, **kw):
    return {"tipo": tipo, "origem": origem, "destino": destino, "confianca": 0.9, **kw}


def test_validar_mantem_relacao_valida_e_preenche_desconhecida():
    e, descartes = validar(_ext([COZAAR, TONTURA], [rel("PODE_CAUSAR", "cozaar", "tontura")]),
                           "cozaar")
    assert descartes == [] and e.relacoes[0].frequencia == "desconhecida"


@pytest.mark.parametrize("entidades,relacao,motivo", [
    ([COZAAR], rel("PODE_CAUSAR", "cozaar", "tontura"), "ponta fora"),
    ([COZAAR, {"id": "hipertensao", "label": "Condicao", "nome": "H"}],
     rel("PODE_CAUSAR", "cozaar", "hipertensao"), "fora do schema"),
    ([COZAAR, {"id": "crianca", "label": "Populacao", "nome": "Criança"}],
     rel("CONTRAINDICADO_EM", "cozaar", "crianca"), "Populacao"),
    ([{"id": "renitec", "label": "Medicamento", "nome": "Renitec"}, TONTURA],
     rel("PODE_CAUSAR", "renitec", "tontura"), "não é o da bula"),
    ([{"id": "losartana", "label": "PrincipioAtivo", "nome": "Losartana"}],
     rel("INTERAGE_COM", "losartana", "losartana"), "laço"),
])
def test_validar_descarta_fora_do_schema(entidades, relacao, motivo):
    e, descartes = validar(_ext(entidades, [relacao]), "cozaar")
    assert e.relacoes == [] and e.entidades == []
    assert any(motivo in d for d in descartes), descartes


def test_validar_normaliza_ids_apaga_prop_errada_e_deduplica():
    ents = [{"id": "Cozaar", "label": "Medicamento", "nome": "Cozaar"},
            {"id": "Insuficiência Renal", "label": "Condicao", "nome": "Insuficiência renal"}]
    rels = [rel("CONTRAINDICADO_EM", "Cozaar", "Insuficiência Renal", dose="50 mg"),
            rel("CONTRAINDICADO_EM", "cozaar", "insuficiencia_renal", confianca=1.0)]
    e, descartes = validar(_ext(ents, rels), "cozaar")
    assert [(r.origem, r.destino, r.dose, r.confianca) for r in e.relacoes] == [
        ("cozaar", "insuficiencia_renal", None, 1.0)]
    assert {x.id for x in e.entidades} == {"cozaar", "insuficiencia_renal"}
    assert any("dose apagada" in d for d in descartes) and any("repetida" in d for d in descartes)


def test_exemplos_passam_na_validacao_sem_descarte():
    for med, _, _, saida in EXEMPLOS:
        limpa, descartes = validar(saida, med)
        assert descartes == [] and len(limpa.relacoes) == len(saida.relacoes)
