from pathlib import Path

import pytest

pytest.importorskip("pyvis")
pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

from graphrag_bulas import api, interface  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")

R = {
    "modo": "graphrag",
    "resposta": "Sim, <b>hemorragia</b>.",
    "subgrafo": {
        "nos": [
            {"id": "marevan", "nome": "Marevan", "labels": ["Medicamento"], "pagerank": 0.4},
            {
                "id": "hemorragia",
                "nome": "Hemorragia",
                "labels": ["EfeitoAdverso"],
                "pagerank": None,
            },
        ],
        "arestas": [
            {"origem": "marevan", "destino": "hemorragia", "tipo": "PODE_CAUSAR", "props": {}}
        ],
    },
    "cypher": "MATCH (m) RETURN m",
    "nos": ["marevan"],
    "confianca": 0.9,
    "recusou": False,
    "trechos": [
        {
            "chunk_id": "c1",
            "texto": "Hemorragia pode ocorrer.",
            "fonte": "bula_marevan",
            "score": None,
            "citado": True,
        },
        {
            "chunk_id": "c2",
            "texto": "Outro.",
            "fonte": "bula_marevan",
            "score": 0.5,
            "citado": False,
        },
    ],
}


def test_resposta_escapa_html_e_mostra_confianca():
    html = interface.html_resposta(R)
    assert "&lt;b&gt;" in html and "confiança 0.90" in html
    assert "sem base" in interface.html_resposta({**R, "recusou": True})


def test_trechos_so_citados_e_score():
    assert "c2" not in interface.html_trechos(R["trechos"], so_citados=True)
    assert "similaridade 0.50" in interface.html_trechos(R["trechos"])
    assert interface.html_trechos([], so_citados=True) == ""


def test_subgrafo_tem_nos_e_aresta():
    html = interface.html_subgrafo(R["subgrafo"])
    assert "Marevan" in html and "PODE_CAUSAR" in html


def test_app_mostra_dois_modos_e_isola_falha(monkeypatch):
    def falso(pergunta, modo, driver=None, llm=None):
        if modo == "rag":
            raise RuntimeError("sem índice")
        return R

    monkeypatch.setattr(api, "responder", falso)
    monkeypatch.setattr("graphrag_bulas.config.get_driver", lambda: None)
    monkeypatch.setattr("graphrag_bulas.config.get_llm", lambda **kw: None)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input[0].input("O Marevan causa sangramento?")
    at.button[0].click().run()
    html = " ".join(m.value for m in at.markdown)
    assert "&lt;b&gt;hemorragia" in html
    assert "Falhou: RuntimeError: sem índice" in html
    assert "Não substitui" in html
