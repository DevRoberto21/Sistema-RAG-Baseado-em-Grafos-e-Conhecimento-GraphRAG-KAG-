"""GDS no contexto (E5.4): PageRank personalizado, Louvain e caminhos entre medicamentos.

Spec: docs/superpowers/specs/2026-10-28-e5-gds-modo-rag-design.md
"""

from itertools import combinations
from uuid import uuid4

from neo4j.exceptions import Neo4jError

MAX_MEDICAMENTOS = 3
# Ligação entre remédios via princípio ativo, classe e interação (PLANO_EQUIPE, E5.4).
RELACOES_CAMINHO = ["CONTEM", "PERTENCE_A", "INTERAGE_COM"]


def _ler(driver, cypher, **params):
    return driver.execute_query(cypher, params, routing_="r").records


def _projetar(driver, nome, nos, arestas):
    # Nó isolado entra como par (id, None): o OPTIONAL MATCH deixa o destino nulo.
    pares = [[a["origem"], a["destino"], a["tipo"]] for a in arestas]
    pares += [[n["id"], None, None] for n in nos]
    _ler(
        driver,
        """
        UNWIND $pares AS p
        MATCH (a:Entidade {id: p[0]})
        OPTIONAL MATCH (b:Entidade {id: p[1]})
        WITH gds.graph.project(
            $nome, a, b, {relationshipType: p[2]}, {undirectedRelationshipTypes: ['*']}
        ) AS g
        RETURN g.nodeCount AS nos
        """,
        pares=pares,
        nome=nome,
    )


def _caminhos(driver, nome, medicamentos):
    caminhos = []
    for a, b in combinations(medicamentos, 2):
        recs = _ler(
            driver,
            """
            MATCH (a:Entidade {id: $a}), (b:Entidade {id: $b})
            CALL gds.shortestPath.dijkstra.stream(
                $nome, {sourceNode: a, targetNode: b, relationshipTypes: $tipos}
            )
            YIELD nodeIds
            RETURN [n IN gds.util.asNodes(nodeIds) | n.id] AS ids
            LIMIT 1
            """,
            nome=nome,
            a=a,
            b=b,
            tipos=RELACOES_CAMINHO,
        )
        if recs:
            caminhos.append(recs[0]["ids"])
    return caminhos


def ranquear(driver, r):
    """Anota pagerank/comunidade nos nós do subgrafo e grava r["gds"]. Não levanta erro do GDS."""
    nos = r["subgrafo"]["nos"]
    for n in nos:
        n["pagerank"] = n["comunidade"] = None
    r["gds"] = {"caminhos": [], "erro": None}
    if not nos:
        return
    ids = {n["id"] for n in nos}
    seeds = [s for s in r["seeds"] if s in ids]
    medicamentos = [
        s for s in seeds if any(n["id"] == s and "Medicamento" in n["labels"] for n in nos)
    ][:MAX_MEDICAMENTOS]
    nome = f"ctx_{uuid4().hex}"
    try:
        _projetar(driver, nome, nos, r["subgrafo"]["arestas"])
        pr = {
            x["id"]: x["score"]
            for x in _ler(
                driver,
                """
                MATCH (s:Entidade) WHERE s.id IN $seeds
                WITH collect(s) AS fontes
                CALL gds.pageRank.stream($nome, {sourceNodes: fontes})
                YIELD nodeId, score
                RETURN gds.util.asNode(nodeId).id AS id, score
                """,
                nome=nome,
                seeds=seeds,
            )
        }
        com = {
            x["id"]: x["c"]
            for x in _ler(
                driver,
                """
                CALL gds.louvain.stream($nome) YIELD nodeId, communityId
                RETURN gds.util.asNode(nodeId).id AS id, communityId AS c
                """,
                nome=nome,
            )
        }
        caminhos = _caminhos(driver, nome, medicamentos)
    except Neo4jError as e:
        r["gds"]["erro"] = str(e)
        return
    finally:
        try:
            _ler(driver, "CALL gds.graph.drop($nome, false) YIELD graphName", nome=nome)
        except Neo4jError:
            pass  # shortcut: projeção pode vazar se o drop falhar; o catálogo é só memória
    for n in nos:
        n["pagerank"], n["comunidade"] = pr.get(n["id"]), com.get(n["id"])
    r["gds"]["caminhos"] = caminhos
