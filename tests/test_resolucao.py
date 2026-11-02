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
