"""Interface (E6): a mesma pergunta em GraphRAG e RAG tradicional, lado a lado.

Uso:
  uv run --extra ui --extra embeddings streamlit run app/streamlit_app.py
"""

import time
from html import escape

import streamlit as st
import streamlit.components.v1 as components

from graphrag_bulas import api, interface
from graphrag_bulas.config import get_driver, get_llm

MODOS = (("graphrag", "GraphRAG"), ("rag", "RAG tradicional"))

st.set_page_config(page_title="Bulas", layout="wide", initial_sidebar_state="collapsed")
st.markdown(interface.CSS, unsafe_allow_html=True)


@st.cache_resource
def _recursos():
    return get_driver(), get_llm(temperature=0)


def responder(pergunta, modo):
    """Um modo; erro vira {'erro': ...} para a outra coluna seguir funcionando."""
    driver, llm = _recursos()
    t0 = time.monotonic()
    try:
        r = api.responder(pergunta, modo, driver, llm)
    except Exception as e:  # mostrado na coluna, a outra continua
        return {"erro": f"{type(e).__name__}: {e}", "segundos": time.monotonic() - t0}
    return {**r, "segundos": time.monotonic() - t0}


def mostrar(modo, r):
    if "erro" in r:
        st.markdown(interface.html_erro(r["erro"]), unsafe_allow_html=True)
        return
    st.markdown(interface.html_resposta(r, 0), unsafe_allow_html=True)
    if modo == "graphrag":
        if r["subgrafo"]["nos"]:
            components.html(interface.html_subgrafo(r["subgrafo"]), height=430)
        st.markdown(interface.html_cypher(r["cypher"], 2), unsafe_allow_html=True)
        st.markdown(
            interface.html_trechos(r["trechos"], 3, so_citados=True), unsafe_allow_html=True
        )
    else:
        st.markdown(interface.html_trechos(r["trechos"], 1), unsafe_allow_html=True)
    st.markdown(f'<div class="meta">{r["segundos"]:.1f} s</div>', unsafe_allow_html=True)


st.markdown(
    '<h1 class="titulo">Pergunte às bulas.</h1>'
    '<p class="subtitulo">A mesma pergunta respondida de dois jeitos: pelo grafo de '
    "conhecimento e pela busca só nos trechos. 25 bulas da ANVISA.</p>",
    unsafe_allow_html=True,
)

historico = st.session_state.setdefault("historico", [])

with st.form("pergunta", clear_on_submit=True, border=False):
    entrada, botao = st.columns([6, 1], vertical_alignment="bottom")
    pergunta = entrada.text_input(
        "Pergunta", placeholder="O Marevan interage com o Flagyl?", label_visibility="collapsed"
    )
    enviar = botao.form_submit_button("Perguntar", use_container_width=True)

if enviar and pergunta.strip():
    colunas = st.columns(2, gap="large")
    respostas = {}
    for (modo, nome), col in zip(MODOS, colunas, strict=True):
        with col:
            st.markdown(f'<div class="coluna">{nome}</div>', unsafe_allow_html=True)
            with st.spinner("Consultando"):
                respostas[modo] = responder(pergunta.strip(), modo)
            mostrar(modo, respostas[modo])
    historico.insert(0, (pergunta.strip(), respostas))
elif historico:
    ultima, respostas = historico[0]
    st.markdown(
        f'<div class="coluna">Última pergunta</div><p class="resposta">{escape(ultima)}</p>',
        unsafe_allow_html=True,
    )
    for (modo, nome), col in zip(MODOS, st.columns(2, gap="large"), strict=True):
        with col:
            st.markdown(f'<div class="coluna">{nome}</div>', unsafe_allow_html=True)
            mostrar(modo, respostas[modo])

if len(historico) > 1:
    st.markdown(
        '<div class="coluna" style="margin-top:3rem">Anteriores</div>', unsafe_allow_html=True
    )
    for p, rs in historico[1:]:
        corpo = "".join(
            f'<div class="coluna" style="margin-top:1rem">{nome}</div>'
            + (
                interface.html_erro(rs[m]["erro"])
                if "erro" in rs[m]
                else interface.html_resposta(rs[m])
            )
            for m, nome in MODOS
        )
        st.markdown(
            f'<details class="anterior"><summary>{escape(p)}</summary>{corpo}</details>',
            unsafe_allow_html=True,
        )

st.markdown(f'<div class="aviso">{interface.AVISO}</div>', unsafe_allow_html=True)
