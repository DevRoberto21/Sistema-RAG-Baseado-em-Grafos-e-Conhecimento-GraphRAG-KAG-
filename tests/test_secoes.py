import unicodedata

from graphrag_bulas.secoes import separar

BULA = """\
Cabeçalho
1. INDICAÇÕES
Hipertensão.
2. RESULTADOS DE EFICÁCIA
Estudo X.
3. CARACTERÍSTICAS FARMACOLÓGICAS
Meia-vida 2 h.
CONTRAINDICAÇÕES
Gravidez.
5. ADVERTÊNCIAS E
PRECAUÇÕES
Ver item
9. Reações Adversas.
(veja 9. REAÇÕES ADVERSAS).
6. INTERAÇÕES MEDICAMENTOSAS
Varfarina.
7. CUIDADOS DE ARMAZENAMENTO DO MEDICAMENTO
Temperatura ambiente.
\f8. POSOLOGIA E MODO DE USAR
1 comprimido.
12
9. REAÇÕES ADVERSAS
Tontura.
10. SUPERDOSE
Suporte.
DIZERES LEGAIS
Registro 1.0000.0000
Histórico de alteração da bula
4. CONTRAINDICAÇÕES
"""


def test_separa_dez_secoes_em_ordem():
    s = separar(unicodedata.normalize("NFD", BULA))  # acentos decompostos
    assert list(s) == [
        "indicacoes", "resultados_eficacia", "caracteristicas_farmacologicas",
        "contraindicacoes", "advertencias_precaucoes", "interacoes",
        "armazenamento", "posologia", "reacoes_adversas", "superdose",
    ]
    assert s["indicacoes"] == "Hipertensão."
    assert s["contraindicacoes"] == "Gravidez."  # título sem número
    # remissões no corpo não abrem seção nova
    assert "9. Reações Adversas." in s["advertencias_precaucoes"]
    assert "(veja 9. REAÇÕES ADVERSAS)." in s["advertencias_precaucoes"]
    assert s["armazenamento"] == "Temperatura ambiente."  # \f antes do título seguinte
    assert s["posologia"] == "1 comprimido."  # número de página solto removido
    assert s["superdose"] == "Suporte."  # corta em DIZERES LEGAIS e no histórico


def test_texto_sem_titulos():
    assert separar("bula sem estrutura") == {}
