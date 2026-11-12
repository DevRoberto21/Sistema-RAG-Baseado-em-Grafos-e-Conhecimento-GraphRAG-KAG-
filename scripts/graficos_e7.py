"""Gráficos do E7 para o artigo e os slides (E7.5).

Lê docs/resultados/respostas_e7.jsonl e grava PNG em docs/resultados/graficos/.
Uso: uv run python scripts/graficos_e7.py
"""

import json
from pathlib import Path
from statistics import mean, median

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from graphrag_bulas.avaliacao import GOLD, MODOS, _ler_jsonl, metricas  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
RESPOSTAS = RAIZ / "docs" / "resultados" / "respostas_e7.jsonl"
SAIDA = RAIZ / "docs" / "resultados" / "graficos"
NOME = {"graphrag": "GraphRAG", "rag": "RAG", "llm_puro": "LLM puro"}
# Paleta categórica validada (skill dataviz): azul e laranja passam no teste de daltonismo.
AZUL, LARANJA = "#2a78d6", "#eb6834"
TINTA, TINTA2, MUDO, GRADE = "#0b0b0b", "#52514e", "#898781", "#e6e5e1"


def resumo(perguntas, linhas):
    """Métricas por modo, com a mesma regra do relatório: última tentativa vale, erro fica fora."""
    por_id = {p["id"]: p for p in perguntas}
    ultima = {(x["id"], x["modo"]): x for x in linhas if x["id"] in por_id}
    out = {}
    for m in MODOS:
        ls = [x for k, x in ultima.items() if k[1] == m]
        ok = [(por_id[x["id"]]["tipo"], v) for x in ls
              if (v := metricas(por_id[x["id"]], x)) is not None]

        def media(campo, tipo=None, ok=ok):
            return mean(v[campo] for t, v in ok if campo in v and tipo in (None, t))

        out[m] = {"acerto": media("acerto"), "acerto_1hop": media("acerto", "1hop"),
                  "acerto_multihop": media("acerto", "multihop"),
                  "alucinacao": media("alucinacao"), "recusa_falsa": media("recusa_falsa"),
                  "segundos": [x["segundos"] for x in ls]}
    return out


def _eixos(titulo, subtitulo=None):
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=200)
    fig.patch.set_facecolor("white")
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(MUDO)
    ax.tick_params(colors=TINTA2, length=0)
    ax.yaxis.grid(True, color=GRADE, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.suptitle(titulo, x=0.02, ha="left", fontsize=12, color=TINTA, fontweight="bold")
    if subtitulo:
        ax.set_title(subtitulo, loc="left", fontsize=9, color=TINTA2)
    return fig, ax


def _barras(ax, x, alturas, cor, largura, rotulo=None):
    b = ax.bar(x, alturas, largura, color=cor, label=rotulo, edgecolor="white", linewidth=1.5)
    ax.bar_label(b, labels=[f"{h:.2f}" for h in alturas], padding=3, fontsize=8, color=TINTA)


def _salvar(fig, nome):
    fig.tight_layout()
    fig.savefig(SAIDA / nome, facecolor="white")
    plt.close(fig)


def graficos(r):
    SAIDA.mkdir(parents=True, exist_ok=True)
    nomes = [NOME[m] for m in MODOS]
    pos = range(len(MODOS))

    fig, ax = _eixos("Acerto por modo", "Fração das 30 perguntas com resposta no corpus")
    _barras(ax, pos, [r[m]["acerto"] for m in MODOS], AZUL, 0.55)
    ax.set_xticks(pos, nomes)
    ax.set_ylim(0, 1.1)
    _salvar(fig, "1_acerto_por_modo.png")

    fig, ax = _eixos("Acerto por tipo de pergunta", "15 perguntas de 1 salto e 15 de vários saltos")
    w = 0.36
    _barras(ax, [p - w / 2 for p in pos], [r[m]["acerto_1hop"] for m in MODOS], AZUL, w, "1 salto")
    _barras(ax, [p + w / 2 for p in pos], [r[m]["acerto_multihop"] for m in MODOS], LARANJA, w,
            "Vários saltos (multi-hop)")
    ax.set_xticks(pos, nomes)
    ax.set_ylim(0, 1.1)
    ax.legend(frameon=False, fontsize=8, labelcolor=TINTA2, loc="upper right")
    _salvar(fig, "2_acerto_por_tipo.png")

    fig, ax = _eixos("Tempo de resposta por modo",
                     "Segundos por pergunta; a máquina rodava outras tarefas ao mesmo tempo")
    seg = [r[m]["segundos"] for m in MODOS]
    ax.boxplot(seg, tick_labels=nomes, widths=0.45, patch_artist=True,
               boxprops={"facecolor": AZUL, "edgecolor": AZUL},
               medianprops={"color": "white", "linewidth": 2},
               whiskerprops={"color": MUDO}, capprops={"color": MUDO},
               flierprops={"marker": "o", "markersize": 4, "markerfacecolor": MUDO,
                           "markeredgecolor": "white"})
    for i, s in enumerate(seg, 1):
        ax.annotate(f"mediana {median(s):.0f} s", (i + 0.27, median(s)), fontsize=8,
                    color=TINTA, va="center")
    ax.set_ylabel("segundos", color=TINTA2, fontsize=9)
    ax.set_ylim(bottom=0)
    _salvar(fig, "3_tempo_por_modo.png")

    fig, ax = _eixos("Alucinação e recusa falsa",
                     "Alucinação: 10 perguntas sem resposta; recusa falsa: 30 com resposta")
    _barras(ax, [p - w / 2 for p in pos], [r[m]["alucinacao"] for m in MODOS], AZUL, w,
            "Alucinação (respondeu sem base)")
    _barras(ax, [p + w / 2 for p in pos], [r[m]["recusa_falsa"] for m in MODOS], LARANJA, w,
            "Recusa falsa (recusou com base)")
    ax.set_xticks(pos, nomes)
    ax.set_ylim(0, 1.1)
    ax.legend(frameon=False, fontsize=8, labelcolor=TINTA2, loc="upper left")
    _salvar(fig, "4_alucinacao_recusa.png")


if __name__ == "__main__":
    perguntas = json.loads(GOLD.read_text(encoding="utf-8"))["perguntas"]
    r = resumo(perguntas, _ler_jsonl(RESPOSTAS))
    # Os números têm que bater com docs/resultados/avaliacao_e7.md.
    assert round(r["graphrag"]["acerto"], 3) == 0.600, r["graphrag"]["acerto"]
    assert round(r["rag"]["acerto_multihop"], 3) == 0.133, r["rag"]["acerto_multihop"]
    graficos(r)
    print(f"ok: 4 gráficos em {SAIDA.relative_to(RAIZ)}")
