# ruff: noqa: E501  (CSS e HTML inline ficam numa linha por regra)
"""Peças da interface (E6): HTML dos cartões e do subgrafo, sem Streamlit, para testar.

O app em app/streamlit_app.py só monta a página com estas funções.
"""

from html import escape

from pyvis.network import Network

URL_BULARIO = "https://consultas.anvisa.gov.br/#/bulario/"

# Pastéis dessaturados (fundo, texto) por label; o resto cai no cinza.
CORES = {
    "Medicamento": ("#E1F3FE", "#1F6C9F"),
    "PrincipioAtivo": ("#EDF3EC", "#346538"),
    "ClasseTerapeutica": ("#F1EDF7", "#5B4A7A"),
    "Condicao": ("#FBF3DB", "#956400"),
    "EfeitoAdverso": ("#FDEBEC", "#9F2F2D"),
    "Populacao": ("#F3EEE8", "#7A5A3A"),
    "Fabricante": ("#F1F1EF", "#5F5E5B"),
}
CINZA = ("#F1F1EF", "#5F5E5B")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500&display=swap');
:root { --tinta: #111111; --texto: #2F3437; --mudo: #787774; --borda: #EAEAEA; --fundo: #FBFBFA;
        --ease: cubic-bezier(0.16, 1, 0.3, 1); }
html, body, [data-testid="stAppViewContainer"] { background: var(--fundo); }
html, body, .stApp, input, textarea, button {
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif;
  color: var(--texto); }
#MainMenu, footer, header[data-testid="stHeader"], [data-testid="stToolbar"] { display: none; }
.block-container { max-width: 1120px; padding-top: 5rem; padding-bottom: 6rem; }
.aura { position: fixed; inset: -20vmax; pointer-events: none; z-index: 0;
  background: radial-gradient(40vmax 40vmax at 30% 20%, rgba(214, 196, 168, 0.18), transparent 60%);
  animation: deriva 28s ease-in-out infinite alternate; }
@keyframes deriva { to { transform: translate3d(12vmax, 8vmax, 0); } }
@keyframes surgir { from { opacity: 0; transform: translateY(12px); }
                    to { opacity: 1; transform: none; } }
.titulo { font-family: 'Newsreader', serif; font-weight: 400; font-size: 3.4rem; line-height: 1.1;
  letter-spacing: -0.03em; color: var(--tinta); margin: 0; animation: surgir 700ms var(--ease) both; }
.subtitulo { color: var(--mudo); font-size: 1.05rem; line-height: 1.6; margin: 0.8rem 0 2.6rem;
  animation: surgir 700ms var(--ease) 80ms both; }
.stTextInput input { border: 1px solid var(--borda) !important; border-radius: 12px !important;
  background: #FFFFFF !important; padding: 0.9rem 1.1rem !important; font-size: 1.05rem !important;
  transition: border-color 200ms var(--ease); box-shadow: none !important;
  color: var(--tinta) !important; -webkit-text-fill-color: var(--tinta) !important; caret-color: var(--tinta); }
.stTextInput input::placeholder { color: #A8A6A1 !important; -webkit-text-fill-color: #A8A6A1 !important; }
.stTextInput input:focus { border-color: #BDBBB6 !important; }
.stButton button, .stFormSubmitButton button { background: var(--tinta); color: #FFFFFF;
  border: none; border-radius: 6px; padding: 0.55rem 1.3rem; transition: background 200ms, transform 120ms; }
.stButton button:hover, .stFormSubmitButton button:hover { background: #333333; color: #FFFFFF; }
.stButton button:active, .stFormSubmitButton button:active { transform: scale(0.98); }
.coluna { font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--mudo);
  margin-bottom: 0.7rem; }
.cartao { position: relative; background: #FFFFFF; border: 1px solid var(--borda); border-radius: 12px;
  padding: 28px; margin-bottom: 14px; animation: surgir 600ms var(--ease) both;
  animation-delay: calc(var(--i, 0) * 80ms); transition: box-shadow 200ms var(--ease); }
.cartao:hover { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04); }
.resposta { font-size: 1.02rem; line-height: 1.6; color: var(--texto); white-space: pre-wrap; }
.etiqueta { display: inline-block; border-radius: 9999px; padding: 3px 10px; font-size: 0.68rem;
  letter-spacing: 0.05em; text-transform: uppercase; margin: 0 6px 12px 0; }
.trecho { border-top: 1px solid var(--borda); padding: 14px 0 4px; font-size: 0.9rem;
  line-height: 1.6; color: var(--texto); }
.trecho:first-of-type { border-top: none; }
.meta { font-family: 'SF Mono', 'JetBrains Mono', monospace; font-size: 0.74rem; color: var(--mudo); }
.meta a { color: var(--mudo); text-decoration: none; border-bottom: 1px solid var(--borda); }
.cypher { font-family: 'SF Mono', 'JetBrains Mono', monospace; font-size: 0.78rem; line-height: 1.6;
  background: #F7F6F3; border-radius: 8px; padding: 14px 16px; white-space: pre-wrap;
  word-break: break-word; color: var(--texto); }
.erro { color: #9F2F2D; }
.aviso { margin-top: 4rem; padding-top: 1.4rem; border-top: 1px solid var(--borda); color: var(--mudo);
  font-size: 0.85rem; line-height: 1.6; }
details.anterior { border-bottom: 1px solid var(--borda); padding: 14px 0; }
details.anterior summary { cursor: pointer; list-style: none; color: var(--texto); }
details.anterior summary::before { content: '+'; display: inline-block; width: 1.4rem; color: var(--mudo); }
details.anterior[open] summary::before { content: '\\2212'; }
</style>
<div class="aura"></div>
"""

AVISO = (
    "Este sistema responde só com base em bulas da ANVISA e pode errar. "
    "Não substitui a orientação de médico ou farmacêutico."
)


def etiqueta(texto, label=None):
    fundo, cor = CORES.get(label, CINZA)
    return f'<span class="etiqueta" style="background:{fundo};color:{cor}">{escape(texto)}</span>'


def etiquetas_resposta(r):
    """Confiança e recusa como etiquetas pastel."""
    if r["recusou"]:
        return etiqueta("sem base nas bulas", "EfeitoAdverso")
    conf = r.get("confianca")
    tom = "PrincipioAtivo" if conf is not None and conf >= 0.7 else "Condicao"
    return etiqueta(f"confiança {conf:.2f}" if conf is not None else "confiança —", tom)


def cartao(conteudo, i=0):
    return f'<div class="cartao" style="--i:{i}">{conteudo}</div>'


def html_resposta(r, i=0):
    return cartao(etiquetas_resposta(r) + f'<div class="resposta">{escape(r["resposta"])}</div>', i)


def html_trechos(trechos, i=0, so_citados=False):
    """Trechos com a bula de origem; em so_citados, só os que a resposta cita."""
    ts = [t for t in trechos if t.get("citado") or not so_citados]
    if not ts:
        return ""
    itens = []
    for t in ts:
        meta = [
            f'<a href="{URL_BULARIO}" target="_blank">{escape(t.get("fonte") or "bula")}</a>',
            escape(t["chunk_id"]),
        ]
        if t.get("score") is not None:
            meta.append(f"similaridade {t['score']:.2f}")
        if t.get("citado"):
            meta.append("citado")
        texto = t["texto"] if len(t["texto"]) <= 420 else t["texto"][:420].rstrip() + "…"
        itens.append(
            f'<div class="trecho"><div class="meta">{" · ".join(meta)}</div>{escape(texto)}</div>'
        )
    return cartao('<div class="coluna">Trechos</div>' + "".join(itens), i)


def html_cypher(cypher, i=0):
    if not cypher:
        return ""
    return cartao(
        f'<div class="coluna">Cypher gerado</div><div class="cypher">{escape(cypher)}</div>', i
    )


def html_erro(erro, i=0):
    return cartao(f'<div class="resposta erro">Falhou: {escape(erro)}</div>', i)


def html_subgrafo(subgrafo, altura=420):
    """Subgrafo interativo (vis-network via pyvis), cor por label, nó maior com mais PageRank."""
    net = Network(
        height=f"{altura}px",
        width="100%",
        bgcolor="#FFFFFF",
        font_color="#2F3437",
        directed=True,
        cdn_resources="remote",
    )
    ranks = [n.get("pagerank") or 0.0 for n in subgrafo["nos"]] or [0.0]
    topo = max(ranks) or 1.0
    for n in subgrafo["nos"]:
        label = (n.get("labels") or [None])[0]
        fundo, cor = CORES.get(label, CINZA)
        net.add_node(
            n["id"],
            label=n.get("nome") or n["id"],
            title=f"{label}: {n['id']}",
            color={
                "background": fundo,
                "border": cor,
                "highlight": {"background": fundo, "border": "#111111"},
            },
            font={"color": cor, "face": "-apple-system, Helvetica Neue, sans-serif"},
            size=10 + 18 * (n.get("pagerank") or 0.0) / topo,
            shape="dot",
            borderWidth=1,
        )
    ids = {n["id"] for n in subgrafo["nos"]}
    for a in subgrafo["arestas"]:
        if a["origem"] in ids and a["destino"] in ids:
            net.add_edge(a["origem"], a["destino"], title=a["tipo"], color="#D9D8D4", width=1)
    net.set_options("""{"physics": {"barnesHut": {"springLength": 110}, "stabilization": {"iterations": 120}},
                        "interaction": {"hover": true}, "edges": {"smooth": {"type": "continuous"},
                        "arrows": {"to": {"scaleFactor": 0.4}}}}""")
    html = net.generate_html()
    # Entrada suave do canvas, no mesmo ritmo dos cartões.
    return html.replace(
        "<body>",
        '<body style="margin:0;animation:surgir 700ms cubic-bezier(0.16,1,0.3,1) both">'
        "<style>@keyframes surgir{from{opacity:0;transform:translateY(12px)}to{opacity:1}}"
        "#mynetwork{border:none!important}</style>",
        1,
    )
