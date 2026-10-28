"""Retrieval do GraphRAG (E5.1 + E5.2): seeds híbridas e expansão multi-hop. Só leitura.

Spec: docs/superpowers/specs/2026-10-28-e5-retrieval-seeds-expansao-design.md
"""

import re

from graphrag_bulas.embeddings import embed

# Limiares calibrados na sondagem de 2026-10-28 sobre o grafo semente; recalibrar após o M2.
MIN_SCORE_VETOR = 0.75  # acertos ~0.79-0.83, ruído ~0.66-0.73
MIN_LETRAS_TERMO = 4  # índice sem stopwords: "a"/"de" casariam com fabricante e sinônimos
TOP_VETOR = 10
TOP_FULLTEXT = 10
RELACOES_DOMINIO = [
    "CONTEM",
    "PERTENCE_A",
    "INTERAGE_COM",
    "INDICADO_PARA",
    "CONTRAINDICADO_EM",
    "PODE_CAUSAR",
    "FABRICADO_POR",
]


def _ler(driver, cypher, **params):
    return driver.execute_query(cypher, params, routing_="r").records


def termos_fulltext(pergunta):
    """Palavras com 4+ letras, unidas por espaço (OR no Lucene).

    \\w+ já remove os caracteres especiais do Lucene, e o filtro de tamanho remove AND/OR/NOT.
    """
    return " ".join(w for w in re.findall(r"\w+", pergunta) if len(w) >= MIN_LETRAS_TERMO)


def _juntar(seeds, r, fonte):
    s = seeds.setdefault(
        r["id"],
        {
            "id": r["id"],
            "nome": r["nome"],
            "labels": [],
            "fontes": [],
            "score_vetor": None,
            "score_fulltext": None,
        },
    )
    s["labels"] += [lb for lb in r["labels"] if lb not in s["labels"]]
    if fonte not in s["fontes"]:
        s["fontes"].append(fonte)
    chave = f"score_{fonte}"
    s[chave] = max(s[chave] or 0.0, r["score"])


def buscar_seeds(driver, pergunta, k_chunks=5):
    """E5.1: entidades (vetor + fulltext) e chunks (vetor) mais próximos da pergunta."""
    if not re.search(r"\w", pergunta):
        return {"entidades": [], "chunks": []}
    v = embed([pergunta])[0]
    seeds = {}
    for r in _ler(
        driver,
        """
        CALL db.index.vector.queryNodes('entidade_embedding', $k, $v) YIELD node, score
        WHERE score >= $min
        RETURN node.id AS id, node.nome AS nome,
               [lb IN labels(node) WHERE lb <> 'Entidade'] AS labels, score
        """,
        k=TOP_VETOR,
        v=v,
        min=MIN_SCORE_VETOR,
    ):
        _juntar(seeds, r, "vetor")
    termos = termos_fulltext(pergunta)
    if termos:
        for r in _ler(
            driver,
            """
            CALL db.index.fulltext.queryNodes('entidade_nomes', $t) YIELD node, score
            RETURN node.id AS id, node.nome AS nome,
                   [lb IN labels(node) WHERE lb <> 'Entidade'] AS labels, score
            LIMIT $k
            """,
            t=termos,
            k=TOP_FULLTEXT,
        ):
            _juntar(seeds, r, "fulltext")
    entidades = sorted(
        seeds.values(), key=lambda s: (-len(s["fontes"]), -(s["score_vetor"] or 0.0), s["id"])
    )
    chunks = [
        dict(r)
        for r in _ler(
            driver,
            """
            CALL db.index.vector.queryNodes('chunk_embedding', $k, $v) YIELD node, score
            OPTIONAL MATCH (b:Bula)-[:TEM_SECAO]->(:Secao)-[:TEM_CHUNK]->(node)
            RETURN node.id AS chunk_id, node.texto AS texto, b.id AS fonte, score
            ORDER BY score DESC
            """,
            k=k_chunks,
            v=v,
        )
    ]
    return {"entidades": entidades, "chunks": chunks}


def expandir(driver, seeds, saltos=2, max_nos=60):
    """E5.2: vizinhança de até `saltos` saltos das seeds, só por relações de domínio."""
    ids = [s["id"] for s in seeds["entidades"]]
    nos, arestas = [], []
    if ids:
        rels = "|".join(RELACOES_DOMINIO)
        nos = [
            dict(r)
            for r in _ler(
                driver,
                f"""
                CALL {{
                  MATCH (s:Entidade) WHERE s.id IN $ids RETURN s AS n, 0 AS d
                  UNION ALL
                  MATCH (s:Entidade) WHERE s.id IN $ids
                  MATCH p = (s)-[:{rels}*1..{int(saltos)}]-(n:Entidade)
                  RETURN n, length(p) AS d
                }}
                WITH n, min(d) AS dist
                ORDER BY dist, n.id
                LIMIT $max
                RETURN elementId(n) AS eid, n.id AS id, n.nome AS nome,
                       [lb IN labels(n) WHERE lb <> 'Entidade'] AS labels, dist
                """,
                ids=ids,
                max=max_nos,
            )
        ]
        # shortcut: aresta aponta por id, ambíguo se o id existe em 2 labels (ex.: cefaleia).
        arestas = [
            dict(r)
            for r in _ler(
                driver,
                """
                MATCH (a)-[r]->(b)
                WHERE elementId(a) IN $eids AND elementId(b) IN $eids AND type(r) IN $tipos
                RETURN a.id AS origem, b.id AS destino, type(r) AS tipo, properties(r) AS props
                ORDER BY origem, tipo, destino
                """,
                eids=[n["eid"] for n in nos],
                tipos=RELACOES_DOMINIO,
            )
        ]
        for n in nos:
            del n["eid"]
    citados = list(
        dict.fromkeys(
            a["props"]["fonte_chunk_id"] for a in arestas if a["props"].get("fonte_chunk_id")
        )
    )
    trechos = [
        {**dict(r), "score": None}
        for r in _ler(
            driver,
            """
            UNWIND $ids AS cid
            MATCH (c:Chunk {id: cid})
            OPTIONAL MATCH (b:Bula)-[:TEM_SECAO]->(:Secao)-[:TEM_CHUNK]->(c)
            RETURN c.id AS chunk_id, c.texto AS texto, b.id AS fonte
            """,
            ids=citados,
        )
    ]
    vistos = {t["chunk_id"] for t in trechos}
    trechos += [c for c in seeds["chunks"] if c["chunk_id"] not in vistos]
    return {"seeds": ids, "subgrafo": {"nos": nos, "arestas": arestas}, "trechos": trechos}


def recuperar(driver, pergunta):
    """Pergunta -> seeds -> subgrafo + trechos. Entrada da parte 2 do E5."""
    return expandir(driver, buscar_seeds(driver, pergunta))
