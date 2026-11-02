"""Resolução de entidades (E4.1, E4.2). Sem Neo4j e sem modelo: embedding falso."""

import pytest

from graphrag_bulas import resolucao as rz


@pytest.mark.parametrize(
    "id_,label,esperado",
    [
        ("losartana_potassica", "PrincipioAtivo", "losartana"),
        ("carbonato_de_litio", "PrincipioAtivo", "litio"),
        ("olmesartana_medoxomila", "PrincipioAtivo", "olmesartana"),
        ("aines", "ClasseTerapeutica", "aine"),
        ("betabloqueadores", "ClasseTerapeutica", "betabloqueador"),
        ("bloqueadores_dos_canais_de_calcio", "ClasseTerapeutica", "bloqueador_do_canal_de_calcio"),
        ("inhibidores_da_eca", "ClasseTerapeutica", "inibidor_da_eca"),
        ("diabetes", "Condicao", "diabetes"),
        ("Insuficiência Renal", "Condicao", "insuficiencia_renal"),
    ],
)
def test_normalizar(id_, label, esperado):
    assert rz.normalizar(id_, label) == esperado


@pytest.mark.parametrize(
    "a,b,esperado",
    [
        ("hipertensao", "hipotensao", True),
        ("hipocalemia", "hipercalemia", True),
        ("bradicardia", "taquicardia", True),
        ("tontura", "vertigem", False),
    ],
)
def test_bloqueado(a, b, esperado):
    assert rz.bloqueado(a, b) is esperado


def test_carregar_dicionario_normaliza_variantes_e_inclui_nome_comercial(tmp_path):
    arq = tmp_path / "sinonimos.json"
    arq.write_text(
        '{"ClasseTerapeutica": {"aine": ["AINEs", "anti-inflamatórios não esteroides"]}}'
    )
    dic = rz.carregar_dicionario(arq)
    assert dic["ClasseTerapeutica"] == {"aine": "aine", "anti_inflamatorio_nao_esteroide": "aine"}
    assert dic["PrincipioAtivo"]["cipro"] == "ciprofloxacino"
    assert "bactrim" not in dic["PrincipioAtivo"]  # dois princípios ativos: ambíguo


def test_dicionario_do_repo_carrega():
    dic = rz.carregar_dicionario()
    assert dic["ClasseTerapeutica"]["inibidor_da_eca"] == "ieca"
    assert dic["Fabricante"]["organon_farmaceutica_ltda"] == "organon"
