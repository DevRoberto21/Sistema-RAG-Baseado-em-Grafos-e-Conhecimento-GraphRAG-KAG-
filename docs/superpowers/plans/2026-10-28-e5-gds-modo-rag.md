# E5.4 + E5.8 — GDS no contexto e modo `rag` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar o E5. O modo `rag` (RAG tradicional, só vetor) entra no `responder`. O GDS (PageRank personalizado, Louvain e caminho mais curto entre medicamentos) passa a ordenar e enriquecer o contexto do modo `graphrag`.

**Architecture:** E5.8 troca só o retrieval: `recuperar_vetorial` devolve o mesmo formato de `recuperar`, com subgrafo vazio, e reusa `montar_contexto` e `gerar_resposta`. E5.4 é um módulo novo, `gds.py`, com `ranquear(driver, r)`. Ele projeta só o subgrafo da pergunta, anota `pagerank`/`comunidade` nos nós e grava `r["gds"]["caminhos"]`. `montar_contexto` ordena os fatos por PageRank e põe os caminhos num bloco próprio.

**Tech Stack:** Python 3.12, driver `neo4j` 6.x, Neo4j GDS 2.13 (`gds.graph.project` por agregação Cypher, `gds.pageRank.stream`, `gds.louvain.stream`, `gds.shortestPath.dijkstra.stream`), bge-m3 via `embed()`, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-28-e5-gds-modo-rag-design.md`

**Status de validação:** o código final deste plano rodou em 2026-10-28 numa cópia do repo, contra o grafo semente: suíte com 77 passed e 2 skipped, ruff e format limpos. Se um teste falhar, investigue o ambiente (Neo4j de pé, semente carregado, GDS no `docker-compose`) antes de mudar a lógica.

## Global Constraints

- Branch: `e5/gds-modo-rag`, criada a partir da `main` (a spec já está commitada na `main`).
- Commits em pt-BR, semânticos (`feat:`, `test:`, `docs:`), **sem** linha `Co-Authored-By` nem assinatura do Claude.
- Lint: `uv run ruff check .` limpo e `uv run ruff format --check src tests` limpo (linha máx. 100).
- Testes com Neo4j usam a fixture `db` de `tests/conftest.py`: pulam sem Neo4j ou sem grafo semente. Antes: Docker ligado e `docker compose up -d`. Rodar tudo com `uv run`.
- `tests/` não tem `__init__.py`: `from test_geracao import LLMFalso, resp` funciona.
- Todas as queries do GDS usam `routing_="r"` (transação só leitura). A projeção, o stream e o `gds.graph.drop` rodam assim; a sondagem confirmou.
- Constantes da spec: `MAX_MEDICAMENTOS = 3`, `RELACOES_CAMINHO = ["CONTEM", "PERTENCE_A", "INTERAGE_COM"]`, `k=5` no modo `rag`, nome da projeção `ctx_<uuid4 hex>`.
- `ranquear` nunca levanta erro do Neo4j/GDS (`neo4j.exceptions.Neo4jError`): grava em `r["gds"]["erro"]`.
- Contrato de `responder`: as chaves continuam exatamente `modo, resposta, subgrafo, cypher, nos, confianca, recusou, trechos`.

## File Structure

| Arquivo | Ação | Task | Responsabilidade |
|---|---|---|---|
| `src/graphrag_bulas/retrieval.py` | modificar | 1, 3 | extrai `buscar_chunks`; `recuperar` chama `ranquear` |
| `src/graphrag_bulas/rag_vetorial.py` | criar | 1 | `recuperar_vetorial(driver, pergunta, k=5)` |
| `tests/test_rag_vetorial.py` | criar | 1 | 2 testes |
| `src/graphrag_bulas/geracao.py` | modificar | 2 | confiança sem nós quando o contexto não tem nós |
| `src/graphrag_bulas/api.py` | modificar | 2 | `modo="rag"` |
| `tests/test_geracao.py`, `tests/test_api.py` | modificar | 2 | +1 teste cada; sai `test_modo_rag_ainda_nao_existe` |
| `README.md` | modificar | 2 | exemplo do modo `rag` |
| `src/graphrag_bulas/gds.py` | criar | 3 | `ranquear(driver, r)` |
| `tests/test_gds.py` | criar | 3 | 3 testes |
| `tests/test_retrieval.py` | modificar | 3 | +1 teste |
| `src/graphrag_bulas/contexto.py` | modificar | 4 | ordem por `pagerank`; bloco de caminhos |
| `tests/test_contexto.py` | modificar | 4 | +2 testes |

---

### Task 1: `buscar_chunks` e `recuperar_vetorial` (E5.8, retrieval)

**Files:**
- Modify: `src/graphrag_bulas/retrieval.py` (fim de `buscar_seeds`, hoje linhas 94–108)
- Create: `src/graphrag_bulas/rag_vetorial.py`
- Test: `tests/test_rag_vetorial.py`

**Interfaces:**
- Consumes: `embed(textos) -> list[list[float]]` (`embeddings.py`); `_ler(driver, cypher, **params)` (`retrieval.py`).
- Produces: `buscar_chunks(driver, vetor, k) -> list[{"chunk_id", "texto", "fonte", "score"}]` em `retrieval.py`; `recuperar_vetorial(driver, pergunta, k=5) -> {"seeds": [], "subgrafo": {"nos": [], "arestas": []}, "trechos": list, "cypher": None}` em `rag_vetorial.py`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_rag_vetorial.py`:

```python
"""Modo rag (E5.8): top-k chunks sem grafo. Pula sem Neo4j (fixture db em conftest.py)."""

from graphrag_bulas import rag_vetorial
from graphrag_bulas.rag_vetorial import recuperar_vetorial


def test_top_k_por_score_sem_grafo(db):
    r = recuperar_vetorial(db, "Posso tomar Marevan com Advil?", k=3)
    assert r["subgrafo"] == {"nos": [], "arestas": []} and r["cypher"] is None
    scores = [t["score"] for t in r["trechos"]]
    assert len(scores) == 3 and scores == sorted(scores, reverse=True)
    assert all(t["fonte"].startswith("bula_") for t in r["trechos"])


def test_pergunta_sem_palavras_nao_chama_embed(monkeypatch):
    def falha(_):
        raise AssertionError("embed chamado")

    monkeypatch.setattr(rag_vetorial, "embed", falha)
    assert recuperar_vetorial(None, "?!")["trechos"] == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_rag_vetorial.py -v`
Expected: erro de coleta `ModuleNotFoundError: No module named 'graphrag_bulas.rag_vetorial'`.

- [ ] **Step 3: Extrair `buscar_chunks` em `retrieval.py`**

No fim de `buscar_seeds`, trocar este bloco:

```python
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
```

por:

```python
    return {"entidades": entidades, "chunks": buscar_chunks(driver, v, k_chunks)}


def buscar_chunks(driver, vetor, k):
    """Top-k chunks do índice vetorial, com a bula de origem. Usado pelos modos graphrag e rag."""
    return [
        dict(r)
        for r in _ler(
            driver,
            """
            CALL db.index.vector.queryNodes('chunk_embedding', $k, $v) YIELD node, score
            OPTIONAL MATCH (b:Bula)-[:TEM_SECAO]->(:Secao)-[:TEM_CHUNK]->(node)
            RETURN node.id AS chunk_id, node.texto AS texto, b.id AS fonte, score
            ORDER BY score DESC
            """,
            k=k,
            v=vetor,
        )
    ]
```

A query não muda: os dois modos usam a mesma busca, então a comparação do E7 é justa.

- [ ] **Step 4: Criar `src/graphrag_bulas/rag_vetorial.py`**

```python
"""Modo rag (E5.8): RAG tradicional, top-k chunks por similaridade, sem grafo.

Spec: docs/superpowers/specs/2026-10-28-e5-gds-modo-rag-design.md
"""

import re

from graphrag_bulas.embeddings import embed
from graphrag_bulas.retrieval import buscar_chunks


def recuperar_vetorial(driver, pergunta, k=5):
    """Mesmo formato de recuperar(), com subgrafo vazio e sem Cypher."""
    trechos = buscar_chunks(driver, embed([pergunta])[0], k) if re.search(r"\w", pergunta) else []
    return {"seeds": [], "subgrafo": {"nos": [], "arestas": []}, "trechos": trechos, "cypher": None}
```

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/test_rag_vetorial.py tests/test_retrieval.py -v`
Expected: todos passam (`test_retrieval.py` confere que `buscar_seeds` segue igual; o teste com `llm` real do E5.3 aparece como skipped). O bge-m3 carrega na primeira vez; pode levar minutos.

- [ ] **Step 6: Lint e commit**

```bash
uv run ruff check . && uv run ruff format --check src tests
git add src/graphrag_bulas/retrieval.py src/graphrag_bulas/rag_vetorial.py tests/test_rag_vetorial.py
git commit -m "feat: adiciona recuperar_vetorial do modo rag com buscar_chunks compartilhado (E5.8)"
```

---

### Task 2: modo `rag` no `responder` e confiança sem nós (E5.8, API)

**Files:**
- Modify: `src/graphrag_bulas/geracao.py` (linha `citadas = ...` em `gerar_resposta`)
- Modify: `src/graphrag_bulas/api.py`
- Modify: `tests/test_geracao.py`, `tests/test_api.py`
- Modify: `README.md` (bloco "Resposta completa (E5.5 + E5.6 + E5.7)")

**Interfaces:**
- Consumes: `recuperar_vetorial(driver, pergunta, k=5)` (Task 1); `gerar_resposta(llm, pergunta, contexto)` e `montar_contexto(r)` (existentes); `LLMFalso`, `resp` de `tests/test_geracao.py`.
- Produces: `responder(pergunta, modo="graphrag" | "rag", driver=None, llm=None)`; modo fora desses levanta `ValueError("modo desconhecido: ...")`.

- [ ] **Step 1: Escrever os testes que falham**

No fim de `tests/test_geracao.py`, acrescentar:

```python


def test_contexto_sem_nos_nao_penaliza_nos_citados():
    llm = LLMFalso(Resposta=[resp(chunks=["c1"], nos=["marevan", "x"])])
    g = gerar_resposta(llm, "p", {**CTX, "nos": set()})
    assert g["confianca"] == 1.0 and g["nos"] == []
```

Em `tests/test_api.py`, trocar o teste:

```python
def test_modo_rag_ainda_nao_existe():
    with pytest.raises(NotImplementedError, match="E5.8"):
        responder("x", modo="rag")
```

por:

```python
def test_responder_modo_rag(db):
    llm = LLMFalso(Resposta=[resp(chunks=["bula_marevan_indicacoes_0"], nos=["marevan"])])
    r = responder(MAREVAN_ADVIL, modo="rag", driver=db, llm=llm)
    assert set(r) == CHAVES and r["modo"] == "rag"
    assert r["subgrafo"] == {"nos": [], "arestas": []} and r["cypher"] is None
    assert r["nos"] == [] and r["recusou"] is False and r["confianca"] == 1.0
    scores = [t["score"] for t in r["trechos"]]
    assert scores == sorted(scores, reverse=True)
    assert [t["chunk_id"] for t in r["trechos"] if t["citado"]] == ["bula_marevan_indicacoes_0"]
    assert len(llm.prompts) == 1  # só a geração; sem Text-to-Cypher
```

`bula_marevan_indicacoes_0` é o chunk mais próximo dessa pergunta no semente (sondagem de 2026-10-28).

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_geracao.py tests/test_api.py -v`
Expected: `test_contexto_sem_nos_nao_penaliza_nos_citados` falha (`confianca` 0.67 em vez de 1.0); `test_responder_modo_rag` falha com `NotImplementedError: modo rag: E5.8`.

- [ ] **Step 3: Implementar a confiança sem nós**

Em `src/graphrag_bulas/geracao.py`, trocar:

```python
    citadas = len(set(r.chunks)) + len(set(r.nos))
```

por:

```python
    # Sem nós no contexto (modo rag), ids de entidade citados não contam contra a confiança.
    citadas = len(set(r.chunks)) + (len(set(r.nos)) if contexto["nos"] else 0)
```

`nos` já sai `[]` nesse caso: o filtro existente só mantém ids que estão em `contexto["nos"]`.

- [ ] **Step 4: Implementar o modo `rag` no `responder`**

Substituir `src/graphrag_bulas/api.py` inteiro por:

```python
"""API única (E5.7, E5.8): responder(pergunta, modo) -> contrato JSON da UI e do E7.

Specs: docs/superpowers/specs/2026-10-28-e5-contexto-geracao-api-design.md
       docs/superpowers/specs/2026-10-28-e5-gds-modo-rag-design.md
"""

from graphrag_bulas.config import get_driver, get_llm
from graphrag_bulas.contexto import montar_contexto
from graphrag_bulas.geracao import gerar_resposta
from graphrag_bulas.rag_vetorial import recuperar_vetorial
from graphrag_bulas.retrieval import recuperar


def responder(pergunta, modo="graphrag", driver=None, llm=None):
    """Pergunta -> resposta citada. "graphrag": grafo + GDS + Cypher; "rag": só vetor (E5.8)."""
    if modo not in ("graphrag", "rag"):
        raise ValueError(f"modo desconhecido: {modo}")
    llm = llm or get_llm(temperature=0)
    if driver is None:
        with get_driver() as d:
            return responder(pergunta, modo, d, llm)
    if modo == "rag":
        r = recuperar_vetorial(driver, pergunta)
    else:
        r = recuperar(driver, pergunta, llm=llm)
    ctx = montar_contexto(r)
    g = gerar_resposta(llm, pergunta, ctx)
    citados = set(g["chunks"])
    return {
        "modo": modo,
        "resposta": g["resposta"],
        "subgrafo": r["subgrafo"],
        "cypher": r["cypher"]["query"] if r["cypher"] else None,
        "nos": g["nos"],
        "confianca": g["confianca"],
        "recusou": g["recusou"],
        "trechos": [{**t, "citado": t["chunk_id"] in citados} for t in ctx["trechos"]],
    }
```

No `README.md`, logo depois da linha do comando `responder('Posso tomar Marevan com Advil?')` (bloco "Resposta completa (E5.5 + E5.6 + E5.7)"), acrescentar uma linha em branco e:

```markdown
Mesma pergunta no RAG tradicional (E5.8), só busca vetorial, sem grafo:

    uv run python -c "from graphrag_bulas.api import responder; import json; print(json.dumps(responder('Posso tomar Marevan com Advil?', modo='rag'), ensure_ascii=False, indent=2))"
```

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/test_geracao.py tests/test_api.py -v`
Expected: todos passam; `test_gemini_real_responde_e_recusa` aparece como skipped. `pytest` continua importado em `tests/test_api.py` (usado por `test_modo_invalido` e pelo `skipif`).

- [ ] **Step 6: Lint e commit**

```bash
uv run ruff check . && uv run ruff format --check src tests
git add src/graphrag_bulas/geracao.py src/graphrag_bulas/api.py tests/test_geracao.py tests/test_api.py README.md
git commit -m "feat: adiciona modo rag ao responder sem penalizar a confiança (E5.8)"
```

---

### Task 3: `ranquear` com PageRank, Louvain e caminhos (E5.4, GDS)

**Files:**
- Create: `src/graphrag_bulas/gds.py`
- Modify: `src/graphrag_bulas/retrieval.py` (imports e `recuperar`)
- Test: `tests/test_gds.py`, `tests/test_retrieval.py`

**Interfaces:**
- Consumes: o dict de `expandir(driver, seeds)`: `{"seeds": [id], "subgrafo": {"nos": [{"id", "nome", "labels", "dist"}], "arestas": [{"origem", "destino", "tipo", "props"}]}, "trechos": [...]}`.
- Produces: `ranquear(driver, r) -> None`, que altera `r` no lugar: cada nó ganha `pagerank: float | None` e `comunidade: int | None`; `r["gds"] = {"caminhos": [[id, ...]], "erro": str | None}`. `recuperar(driver, pergunta, llm=None)` passa a devolver `gds` e os nós anotados. A Task 4 lê `n.get("pagerank")` e `r.get("gds")`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_gds.py`:

```python
"""GDS no contexto (E5.4) sobre o grafo semente. Pula sem Neo4j (fixture db em conftest.py)."""

from types import SimpleNamespace

from graphrag_bulas import gds
from graphrag_bulas.gds import ranquear
from graphrag_bulas.retrieval import buscar_seeds, expandir

MAREVAN_ADVIL = "Posso tomar Marevan com Advil?"


def expandido(db, pergunta=MAREVAN_ADVIL):
    return expandir(db, buscar_seeds(db, pergunta))


def projecoes_ctx(db):
    recs = db.execute_query("CALL gds.graph.list() YIELD graphName RETURN graphName").records
    return [x["graphName"] for x in recs if x["graphName"].startswith("ctx_")]


def test_pagerank_comunidade_e_caminho_marevan_advil(db):
    r = expandido(db)
    ranquear(db, r)
    assert r["gds"]["erro"] is None
    nos = r["subgrafo"]["nos"]
    assert all(n["pagerank"] is not None and n["comunidade"] is not None for n in nos)
    top3 = [n["id"] for n in sorted(nos, key=lambda n: -n["pagerank"])[:3]]
    assert "marevan" in top3
    caminho = next(c for c in r["gds"]["caminhos"] if {c[0], c[-1]} == {"marevan", "advil"})
    assert len(caminho) >= 3
    assert projecoes_ctx(db) == []


def test_subgrafo_vazio_nao_chama_gds():
    r = {"seeds": [], "subgrafo": {"nos": [], "arestas": []}, "trechos": []}
    ranquear(None, r)  # driver None: qualquer chamada ao Neo4j quebraria
    assert r["gds"] == {"caminhos": [], "erro": None}


def test_erro_do_gds_nao_levanta_e_apaga_projecao(db, monkeypatch):
    db.execute_query(
        "CALL gds.graph.project('ctx_fixo', 'Entidade', '*') YIELD graphName RETURN graphName"
    )
    monkeypatch.setattr(gds, "uuid4", lambda: SimpleNamespace(hex="fixo"))
    r = expandido(db)
    ranquear(db, r)  # projeção 'ctx_fixo' já existe: o GDS levanta
    assert r["gds"]["erro"] and r["gds"]["caminhos"] == []
    assert all(n["pagerank"] is None for n in r["subgrafo"]["nos"])
    assert projecoes_ctx(db) == []
```

No fim de `tests/test_retrieval.py`, acrescentar:

```python


def test_recuperar_ranqueia_com_gds(db):
    r = recuperar(db, MAREVAN_ADVIL)
    assert r["gds"]["erro"] is None and r["gds"]["caminhos"]
    assert all(n["pagerank"] is not None for n in r["subgrafo"]["nos"])
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_gds.py tests/test_retrieval.py -v`
Expected: erro de coleta em `test_gds.py`, `ModuleNotFoundError: No module named 'graphrag_bulas.gds'`.

- [ ] **Step 3: Criar `src/graphrag_bulas/gds.py`**

```python
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
```

Notas:
- A projeção sai de `subgrafo.arestas`, que já só tem relações de domínio entre nós do subgrafo. O tipo vira `relationshipType`, e o Dijkstra filtra por `RELACOES_CAMINHO`. Sem esse filtro, o caminho mais curto liga Marevan e Advil por um efeito em comum (`marevan, tontura, advil`); com ele, sai `marevan, varfarina, aine, ibuprofeno, advil`.
- `gds.py` não importa `retrieval.py` (que importa `gds.py`), por isso tem o próprio `_ler`.
- O `id` não é único entre labels (ex.: `cefaleia`, o `shortcut` de `expandir`): o `MATCH` por id pode trazer dois nós, e o dict por id fica com o último. A spec aceita essa limitação.

- [ ] **Step 4: Chamar `ranquear` em `recuperar`**

Em `src/graphrag_bulas/retrieval.py`, acrescentar o import depois de `from graphrag_bulas.embeddings import embed`:

```python
from graphrag_bulas.gds import ranquear
```

E trocar `recuperar` por:

```python
def recuperar(driver, pergunta, llm=None):
    """Pergunta -> seeds -> subgrafo ranqueado (E5.4) + trechos, e o Cypher do LLM (E5.3)."""
    seeds = buscar_seeds(driver, pergunta)
    r = expandir(driver, seeds)
    ranquear(driver, r)
    r["cypher"] = consultar(driver, llm, pergunta, seeds["entidades"]) if llm else None
    return r
```

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/test_gds.py tests/test_retrieval.py -v`
Expected: todos passam (o teste com `llm` real do E5.3 aparece como skipped).

Depois, a suíte inteira: `uv run pytest -q`. Expected: tudo passa; os 2 testes com Gemini real aparecem como skipped.

- [ ] **Step 6: Lint e commit**

```bash
uv run ruff check . && uv run ruff format --check src tests
git add src/graphrag_bulas/gds.py src/graphrag_bulas/retrieval.py tests/test_gds.py tests/test_retrieval.py
git commit -m "feat: adiciona ranquear com PageRank, Louvain e caminhos via GDS (E5.4)"
```

---

### Task 4: contexto ordenado por PageRank e com caminhos (E5.4, contexto)

**Files:**
- Modify: `src/graphrag_bulas/contexto.py`
- Test: `tests/test_contexto.py`

**Interfaces:**
- Consumes: nós de `r["subgrafo"]["nos"]` com `pagerank` opcional (`n.get("pagerank")`); `r.get("gds")` com `{"caminhos": [[id, ...]], "erro": ...}` opcional (Task 3). Sem esses campos (modo `rag`, testes antigos), o comportamento é o do E5.5.
- Produces: `montar_contexto(r, max_fatos=100, max_trechos=20)` com a mesma assinatura e o mesmo dict de saída; `texto` pode começar com o bloco "Caminhos entre medicamentos:"; `nos` inclui os ids dos caminhos.

- [ ] **Step 1: Escrever os testes que falham**

No fim de `tests/test_contexto.py`, acrescentar:

```python


def test_pagerank_maior_vem_primeiro_mesmo_com_dist_maior():
    r = r_base(
        [
            aresta("marevan", "CONTEM", "varfarina", "c1"),  # dist 0
            aresta("varfarina", "INTERAGE_COM", "aine", "c3"),  # dist 1
        ]
    )
    pr = {"marevan": 0.1, "varfarina": 0.2, "aine": 0.9}
    for n in r["subgrafo"]["nos"]:
        n["pagerank"] = pr[n["id"]]
    texto = montar_contexto(r)["texto"]
    assert texto.index("INTERAGE_COM") < texto.index("CONTEM")


def test_bloco_de_caminhos_com_nomes_tipos_e_direcao():
    r = r_base(
        [
            aresta("marevan", "CONTEM", "varfarina", "c1"),
            aresta("aine", "INTERAGE_COM", "varfarina", "c3"),
        ]
    )
    r["gds"] = {"caminhos": [["marevan", "varfarina", "aine", "x"]], "erro": None}
    ctx = montar_contexto(r)
    linha = "- Marevan -[CONTEM]-> Varfarina <-[INTERAGE_COM]- AINEs -[?]- x"
    assert ctx["texto"].startswith("Caminhos entre medicamentos:\n" + linha)
    assert "x" in ctx["nos"]
```

`r_base` e `aresta` já existem no topo do arquivo. Em `r_base`, `aine` tem nome `AINEs`; `x` não está em `subgrafo.nos`, então sai pelo id e sem aresta (`-[?]-`).

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_contexto.py -v`
Expected: os 2 testes novos falham (`CONTEM` vem antes por `dist`; o texto não começa com "Caminhos entre medicamentos:"); os antigos passam.

- [ ] **Step 3: Implementar**

Em `src/graphrag_bulas/contexto.py`:

1. Trocar a docstring do módulo por:

```python
"""Montador de contexto (E5.5): subgrafo + linhas do Cypher + trechos -> texto do prompt.

Specs: docs/superpowers/specs/2026-10-28-e5-contexto-geracao-api-design.md
       docs/superpowers/specs/2026-10-28-e5-gds-modo-rag-design.md (PageRank e caminhos)
"""
```

2. Antes de `def montar_contexto`, acrescentar:

```python
def _caminho(ids, nomes, arestas):
    partes = [nomes.get(ids[0], ids[0])]
    for a, b in zip(ids, ids[1:], strict=False):
        e = next((x for x in arestas if {x["origem"], x["destino"]} == {a, b}), None)
        if e is None:
            seta = "-[?]-"
        elif e["origem"] == a:
            seta = f"-[{e['tipo']}]->"
        else:
            seta = f"<-[{e['tipo']}]-"
        partes += [seta, nomes.get(b, b)]
    return "- " + " ".join(partes)
```

3. Em `montar_contexto`, trocar:

```python
    dist = {n["id"]: n["dist"] for n in nos}
    # shortcut: ordena por dist/confianca; E5.4 troca por PageRank
    arestas = sorted(
        r["subgrafo"]["arestas"],
        key=lambda a: (
            min(dist.get(a["origem"], 99), dist.get(a["destino"], 99)),
```

por:

```python
    dist = {n["id"]: n["dist"] for n in nos}
    pr = {n["id"]: n.get("pagerank") or 0 for n in nos}
    arestas = sorted(
        r["subgrafo"]["arestas"],
        key=lambda a: (
            -max(pr.get(a["origem"], 0), pr.get(a["destino"], 0)),
            min(dist.get(a["origem"], 99), dist.get(a["destino"], 99)),
```

4. Trocar:

```python
    blocos = []
    if arestas:
```

por:

```python
    caminhos = (r.get("gds") or {}).get("caminhos", [])
    blocos = []
    if caminhos:
        blocos.append(
            "Caminhos entre medicamentos:\n"
            + "\n".join(_caminho(c, nomes, r["subgrafo"]["arestas"]) for c in caminhos)
        )
    if arestas:
```

5. No dict de retorno, trocar:

```python
        "nos": {a["origem"] for a in arestas} | {a["destino"] for a in arestas},
```

por:

```python
        "nos": {a["origem"] for a in arestas}
        | {a["destino"] for a in arestas}
        | {i for c in caminhos for i in c},
```

Notas:
- `_caminho` usa todas as arestas do subgrafo, não só as que passaram do corte `max_fatos`; o bloco de caminhos não entra no corte.
- Sem `pagerank` (todos 0), o primeiro termo da chave empata e a ordem é a do E5.5.

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_contexto.py -v`
Expected: 10 passed (8 antigos + 2 novos), incluindo `test_contexto_do_semente_traz_a_interacao_marevan_advil` com o GDS ligado.

Depois: `uv run pytest -q`. Expected: tudo passa; os 2 testes com Gemini real aparecem como skipped.

- [ ] **Step 5: Lint e commit**

```bash
uv run ruff check . && uv run ruff format --check src tests
git add src/graphrag_bulas/contexto.py tests/test_contexto.py
git commit -m "feat: ordena o contexto por PageRank e mostra caminhos entre medicamentos (E5.4)"
```
