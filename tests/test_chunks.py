from graphrag_bulas.chunks import bula_id, chunks_da_bula, quebrar


def test_bula_id_segue_o_seed():
    assert bula_id("bula_Puran T4.pdf") == "bula_puran_t4"
    assert bula_id("bula_renitec.pdf") == "bula_renitec"


def test_quebrar_respeita_limite_e_frases():
    texto = "Primeira frase longa.\nSegunda frase. " * 20 + "x" * 50 + " " + "y" * 50
    pedacos = quebrar(texto, limite=100)
    assert all(len(p) <= 100 for p in pedacos)
    assert pedacos[0].startswith("Primeira frase longa. Segunda frase.")
    assert " ".join(pedacos).split() == texto.split()  # nada perdido
    assert quebrar("") == []


def test_chunks_ids_estaveis_e_so_secoes_do_schema():
    bula = {"arquivo": "bula_Renitec.pdf", "secoes": {
        "advertencias_precaucoes": "Hipotensão. Angioedema.",
        "superdose": "Fora do schema.",
    }}
    cs = chunks_da_bula(bula)
    assert [c["id"] for c in cs] == ["bula_renitec_advertencias_0"]
    assert cs[0]["secao"] == "bula_renitec_advertencias"
    assert chunks_da_bula(bula) == cs  # determinístico
