"""Montador de contexto (E5.5): subgrafo + linhas do Cypher + trechos -> texto do prompt.

Spec: docs/superpowers/specs/2026-10-28-e5-contexto-geracao-api-design.md
"""

import json

PROPS_INTERNAS = {"fonte_chunk_id", "confianca", "metodo"}


def _fato(a, nomes):
    props = {k: v for k, v in sorted(a["props"].items()) if k not in PROPS_INTERNAS}
    tipo = a["tipo"] + (
        " {" + ", ".join(f"{k}: {v}" for k, v in props.items()) + "}" if props else ""
    )
    fonte = a["props"].get("fonte_chunk_id")
    origem, destino = nomes.get(a["origem"], a["origem"]), nomes.get(a["destino"], a["destino"])
    return (
        f"- {origem} -[{tipo}]-> {destino}"
        + (f" [{fonte}]" if fonte else "")
        + f" (ids: {a['origem']}, {a['destino']})"
    )


def montar_contexto(r, max_fatos=100, max_trechos=20):
    """Monta o texto do prompt e os ids que a resposta pode citar. Não acessa o Neo4j."""
    nos = r["subgrafo"]["nos"]
    nomes = {n["id"]: n["nome"] for n in nos}
    dist = {n["id"]: n["dist"] for n in nos}
    # shortcut: ordena por dist/confianca; E5.4 troca por PageRank
    arestas = sorted(
        r["subgrafo"]["arestas"],
        key=lambda a: (
            min(dist.get(a["origem"], 99), dist.get(a["destino"], 99)),
            -(a["props"].get("confianca") or 0),
            a["origem"],
            a["tipo"],
            a["destino"],
        ),
    )[:max_fatos]
    cypher = r.get("cypher") or {}
    linhas = cypher.get("linhas", []) if cypher.get("erro") is None else []

    fontes = [a["props"]["fonte_chunk_id"] for a in arestas if a["props"].get("fonte_chunk_id")]
    ordem = {cid: i for i, cid in enumerate(dict.fromkeys(fontes))}
    trechos = sorted(
        r["trechos"],
        key=lambda t: (
            ordem.get(t["chunk_id"], len(ordem)),
            t["score"] is None,
            -(t["score"] or 0),
        ),
    )
    unicos = {}
    for t in trechos:
        unicos.setdefault(t["chunk_id"], t)
    trechos = list(unicos.values())[:max_trechos]

    blocos = []
    if arestas:
        blocos.append("Fatos do grafo:\n" + "\n".join(_fato(a, nomes) for a in arestas))
    if linhas:
        blocos.append(
            "Resultado da consulta Cypher:\n"
            + "\n".join(
                "- " + json.dumps(linha, ensure_ascii=False, sort_keys=True, default=str)
                for linha in linhas
            )
        )
    if trechos:
        blocos.append(
            "Trechos de bula:\n"
            + "\n".join(f"[{t['chunk_id']}] ({t['fonte']}) {t['texto']}" for t in trechos)
        )
    return {
        "texto": "\n\n".join(blocos),
        "chunk_ids": {t["chunk_id"] for t in trechos}
        | set(fontes)
        | {
            linha["fonte_chunk_id"]
            for linha in linhas
            if isinstance(linha.get("fonte_chunk_id"), str) and linha["fonte_chunk_id"]
        },
        "nos": {a["origem"] for a in arestas} | {a["destino"] for a in arestas},
        "trechos": trechos,
        "sem_consulta": cypher.get("erro") == "sem_consulta",
    }
