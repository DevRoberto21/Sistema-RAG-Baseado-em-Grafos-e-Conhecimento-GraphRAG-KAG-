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


VETORES = {
    "tosse": [1.0, 0.0, 0.0],
    "tosse_seca": [0.9, 0.43589, 0.0],
    "hipotensao": [0.0, 1.0, 0.0],
    "hipertensao": [0.0, 1.0, 0.0],
    "tontura": [0.0, 0.0, 1.0],
}
ITENS = {"tosse": 5, "tosse_seca": 1, "hipotensao": 3, "hipertensao": 2, "tontura": 4}


def test_agrupar_funde_acima_do_limiar_e_respeita_bloqueio():
    mapa, fusoes, pares = rz.agrupar(ITENS, {"tosse"}, VETORES, limiar=0.85)
    assert mapa["tosse_seca"] == "tosse"
    assert mapa["hipertensao"] == "hipertensao"  # vetor igual ao de hipotensao, mas bloqueado
    assert [(de, para) for de, para, _ in fusoes] == [("tosse_seca", "tosse")]
    assert [(i, r) for i, r, _ in pares] == [("tosse_seca", "tosse")]


def test_agrupar_abaixo_do_limiar_so_registra_par():
    mapa, fusoes, pares = rz.agrupar(ITENS, {"tosse"}, VETORES, limiar=0.92)
    assert mapa["tosse_seca"] == "tosse_seca" and fusoes == []
    assert pares[0][:2] == ("tosse_seca", "tosse") and pares[0][2] == pytest.approx(0.9)


def test_agrupar_nunca_funde_dois_canonicos():
    v = {"a": [1.0, 0.0], "b": [1.0, 0.0]}
    mapa, fusoes, _ = rz.agrupar({"a": 1, "b": 1}, {"a", "b"}, v, limiar=0.5)
    assert mapa == {"a": "a", "b": "b"} and fusoes == []


def test_escolher_limiar():
    rot = [(0.95, True), (0.93, True), (0.91, False), (0.90, True)]
    assert rz.escolher_limiar(rot) == 0.93
    assert rz.escolher_limiar([(0.90, False)]) == rz.LIMIAR_PADRAO


def test_ler_rotulados(tmp_path):
    assert rz.ler_rotulados(tmp_path / "nao_existe.csv") is None
    arq = tmp_path / "pares.csv"
    arq.write_text("label,id_a,id_b,cosseno,mesmo\nX,a,b,0.9,s\nX,c,d,0.85,n\nX,e,f,0.82,\n")
    assert rz.ler_rotulados(arq) == [(0.9, True), (0.85, False)]
