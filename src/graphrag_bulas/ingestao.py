"""Ingestão no Neo4j (E4.3, E4.4): grafo.jsonl + documentos -> Neo4j.

Uso:
  uv run --extra embeddings python -m graphrag_bulas.ingestao [--recriar]

Idempotente: só UNWIND + MERGE, em lotes. Aplica cypher/schema.cypher e cypher/seed.cypher,
carrega Bula/Secao/Chunk das bulas de extracoes.jsonl, CONTEM de extracao.COMPOSICAO, nós e
relações de grafo.jsonl, MENCIONA e embeddings. Acrescenta a parte da carga em
logs/relatorio_e4.md. Spec: docs/superpowers/specs/2026-11-01-e4-resolucao-ingestao-design.md
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime

from graphrag_bulas.chunks import PROCESSADOS, bula_id, slug
from graphrag_bulas.config import get_driver
from graphrag_bulas.extracao import COMPOSICAO
from graphrag_bulas.modelos import LABELS, RELACOES
from graphrag_bulas.resolucao import RAIZ, RELATORIO, SAIDA, carregar_dicionario

CYPHER = RAIZ / "cypher"
MANIFESTO = RAIZ / "data" / "raw" / "manifesto.jsonl"
URL_BULARIO = "https://consultas.anvisa.gov.br/#/bulario/"
LOTE = 500
PROPS = ("frequencia", "gravidade", "efeito", "dose", "confianca", "fonte_chunk_id")


def statements(texto: str) -> list[str]:
    """Comandos de um arquivo .cypher: tira linhas de comentário e corta em ';' no fim da linha.

    ';' no meio de string (textos do seed) não corta, porque vem seguido de espaço.
    """
    sem_comentario = "\n".join(x for x in texto.splitlines() if not x.lstrip().startswith("//"))
    return [s.strip() for s in re.split(r";\s*(?:\n|$)", sem_comentario) if s.strip()]


def lotes(itens, n=LOTE):
    for i in range(0, len(itens), n):
        yield itens[i : i + n]


def ler_grafo(path=SAIDA):
    nos, rels = [], []
    for linha in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(linha)
        (nos if item["tipo"] == "no" else rels).append(item)
    return nos, rels


def linhas_bulas(manifesto, bulas, dic_fabricante):
    """Uma linha por bula do escopo, com o Medicamento e o Fabricante do manifesto."""
    rows = []
    for m in manifesto:
        b = bula_id(m["arquivo"])
        if b not in bulas:
            continue
        fab = slug(m["empresa"])
        rows.append(
            {
                "bula": b,
                "med": b.removeprefix("bula_"),
                "nome": m["medicamento"].title(),
                "arquivo": f"data/raw/{m['arquivo']}",
                "registro": m["registro_ms"],
                "data": datetime.strptime(m["data_publicacao"], "%d/%m/%Y").date().isoformat(),
                "fab": dic_fabricante.get(fab, fab),
                "fab_nome": m["empresa"],
            }
        )
    return rows


def linhas_chunks(chunks, bulas):
    return [
        {
            "bula": c["bula"],
            "secao": c["secao"],
            "tipo": c["tipo"],
            "id": c["id"],
            "ordem": c["ordem"],
            "texto": c["texto"],
        }
        for c in chunks
        if c["bula"] in bulas
    ]


def linhas_composicao(nos):
    nomes = {n["id"]: n["nome"] for n in nos if n["label"] == "PrincipioAtivo"}
    return [
        {"med": med, "pa": pa, "nome": nomes.get(pa, pa.replace("_", " ").capitalize())}
        for med, pas in COMPOSICAO.items()
        for pa in pas
    ]


def linhas_menciona(rels):
    """(label, id, chunk) sem repetição: cada chunk menciona as pontas do que sustenta."""
    vistos = set()
    for r in rels:
        for c in r["chunks"]:
            vistos.add((r["label_origem"], r["origem"], c))
            vistos.add((r["label_destino"], r["destino"], c))
    por_label = defaultdict(list)
    for label, i, c in sorted(vistos):
        por_label[label].append({"id": i, "chunk": c})
    return por_label


def _rodar(driver, query, rows, **params):
    for lote in lotes(rows):
        driver.execute_query(query, rows=lote, **params)


def carregar_documentos(driver, bulas_rows, chunk_rows):
    """Bula, Medicamento, Fabricante, Secao e Chunk. Devolve ids de Chunk cujo texto mudou."""
    _rodar(
        driver,
        """
        UNWIND $rows AS r
        MERGE (m:Medicamento {id: r.med})
        ON CREATE SET m:Entidade, m.nome = r.nome, m.sinonimos = [], m.generico = false
        SET m.registro_anvisa = coalesce(m.registro_anvisa, r.registro)
        MERGE (b:Bula {id: r.bula})
        SET b.tipo = 'profissional', b.arquivo = r.arquivo, b.url = $url,
            b.data_publicacao = date(r.data)
        MERGE (b)-[:DESCREVE]->(m)
        MERGE (f:Fabricante {id: r.fab})
        ON CREATE SET f:Entidade, f.nome = r.fab_nome, f.sinonimos = []
        MERGE (m)-[x:FABRICADO_POR]->(f)
        ON CREATE SET x.confianca = 1.0, x.metodo = 'manual'
        """,
        bulas_rows,
        url=URL_BULARIO,
    )
    alterados = []
    for lote in lotes(chunk_rows):
        alterados += [
            r["id"]
            for r in driver.execute_query(
                "UNWIND $rows AS c MATCH (ch:Chunk {id: c.id}) WHERE ch.texto <> c.texto "
                "RETURN ch.id AS id",
                rows=lote,
            ).records
        ]
    _rodar(
        driver,
        """
        UNWIND $rows AS c
        MATCH (b:Bula {id: c.bula})
        MERGE (s:Secao {id: c.secao}) SET s.tipo = c.tipo
        MERGE (b)-[:TEM_SECAO]->(s)
        MERGE (ch:Chunk {id: c.id})
        SET ch.embedding = CASE WHEN ch.texto = c.texto THEN ch.embedding ELSE null END
        SET ch.texto = c.texto, ch.ordem = c.ordem
        MERGE (s)-[:TEM_CHUNK]->(ch)
        """,
        chunk_rows,
    )
    return alterados


def carregar_nos(driver, nos):
    por_label = defaultdict(list)
    for n in nos:
        por_label[n["label"]].append(n)
    for label, rows in por_label.items():
        if label not in LABELS:  # label entra na query por f-string
            raise ValueError(label)
        _rodar(
            driver,
            f"""
            UNWIND $rows AS r
            MERGE (n:{label} {{id: r.id}})
            ON CREATE SET n:Entidade, n.nome = r.nome, n.sinonimos = []
            SET n.sinonimos = n.sinonimos + [s IN r.sinonimos + [r.nome]
                WHERE NOT s IN n.sinonimos AND s <> n.nome]
            """,
            rows,
        )


def carregar_composicao(driver, rows):
    _rodar(
        driver,
        """
        UNWIND $rows AS r
        MATCH (m:Medicamento {id: r.med})
        MERGE (p:PrincipioAtivo {id: r.pa})
        ON CREATE SET p:Entidade, p.nome = r.nome, p.sinonimos = []
        MERGE (m)-[x:CONTEM]->(p)
        ON CREATE SET x.confianca = 1.0, x.metodo = 'manual'
        """,
        rows,
    )


def carregar_rels(driver, rels):
    """MERGE por (tipo, pontas). Relação que já existe (do seed) não é tocada."""
    grupos = defaultdict(list)
    for r in rels:
        props = {p: r[p] for p in PROPS if r.get(p) is not None}
        grupos[r["rel"], r["label_origem"], r["label_destino"]].append(
            {"origem": r["origem"], "destino": r["destino"], "props": props}
        )
    for (rel, lo, ld), rows in grupos.items():
        if rel not in RELACOES or lo not in LABELS or ld not in LABELS:
            raise ValueError((rel, lo, ld))
        _rodar(
            driver,
            f"""
            UNWIND $rows AS r
            MATCH (a:{lo} {{id: r.origem}}), (b:{ld} {{id: r.destino}})
            MERGE (a)-[x:{rel}]->(b)
            ON CREATE SET x += r.props, x.metodo = 'llm'
            """,
            rows,
        )


def carregar_menciona(driver, rels):
    for label, rows in linhas_menciona(rels).items():
        if label not in LABELS:
            raise ValueError(label)
        _rodar(
            driver,
            f"""
            UNWIND $rows AS r
            MATCH (c:Chunk {{id: r.chunk}}), (e:{label} {{id: r.id}})
            MERGE (c)-[:MENCIONA]->(e)
            """,
            rows,
        )


def contar(driver):
    nos = {
        r["label"]: r["n"]
        for r in driver.execute_query(
            "MATCH (n:Entidade) UNWIND [l IN labels(n) WHERE l <> 'Entidade'] AS label "
            "RETURN label, count(*) AS n"
        ).records
    }
    rels = {
        r["tipo"]: r["n"]
        for r in driver.execute_query(
            "MATCH ()-[r]->() RETURN type(r) AS tipo, count(*) AS n"
        ).records
    }
    return nos, rels


def relatorio_carga(alterados, nos_db, rels_db, nos, rels) -> str:
    esperado_nos = defaultdict(int)
    for n in nos:
        esperado_nos[n["label"]] += 1
    esperado_rels = defaultdict(int)
    for r in rels:
        esperado_rels[r["rel"]] += 1
    linhas = [
        "",
        "## Carga no Neo4j",
        "",
        f"Chunks cujo texto mudou (seed resumido -> corpus): {len(alterados)}",
        "",
    ]
    linhas += [f"- {c}" for c in sorted(alterados)]
    linhas += ["", "| Label | grafo.jsonl | Neo4j |", "|---|---|---|"]
    linhas += [
        f"| {k} | {esperado_nos.get(k, 0)} | {nos_db.get(k, 0)} |"
        for k in sorted(set(nos_db) | set(esperado_nos))
    ]
    linhas += ["", "| Relação | grafo.jsonl | Neo4j |", "|---|---|---|"]
    linhas += [
        f"| {k} | {esperado_rels.get(k, 0)} | {rels_db.get(k, 0)} |"
        for k in sorted(set(rels_db) | set(esperado_rels))
    ]
    return "\n".join(linhas) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--recriar", action="store_true", help="apaga o banco antes de carregar")
    a = p.parse_args(argv)

    from graphrag_bulas.embeddings import embed_missing

    nos, rels = ler_grafo()
    bulas = {
        json.loads(x)["bula"] for x in (PROCESSADOS / "extracoes.jsonl").open(encoding="utf-8")
    }
    chunks = [json.loads(x) for x in (PROCESSADOS / "chunks.jsonl").open(encoding="utf-8")]
    manifesto = [json.loads(x) for x in MANIFESTO.open(encoding="utf-8")]
    dic_fab = carregar_dicionario().get("Fabricante", {})

    with get_driver() as driver:
        driver.verify_connectivity()  # Neo4j fora do ar: para aqui com o erro do driver
        if a.recriar:
            driver.execute_query("MATCH (n) DETACH DELETE n")
        for arq in ("schema.cypher", "seed.cypher"):
            for s in statements((CYPHER / arq).read_text(encoding="utf-8")):
                driver.execute_query(s)
        alterados = carregar_documentos(
            driver, linhas_bulas(manifesto, bulas, dic_fab), linhas_chunks(chunks, bulas)
        )
        carregar_nos(driver, nos)
        carregar_composicao(driver, linhas_composicao(nos))
        carregar_rels(driver, rels)
        carregar_menciona(driver, rels)
        print("embeddings:", embed_missing(driver))
        nos_db, rels_db = contar(driver)

    with RELATORIO.open("a", encoding="utf-8") as f:
        f.write(relatorio_carga(alterados, nos_db, rels_db, nos, rels))
    print(f"nós: {nos_db}\nrelações: {rels_db}")


if __name__ == "__main__":
    main()
