# E5 parte 1 — Seeds híbridas e expansão multi-hop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar uma pergunta em seeds (entidades por vetor + fulltext, chunks por vetor) e expandir para um subgrafo de domínio de até 2 saltos com os trechos de bula que o sustentam (E5.1 + E5.2).

**Architecture:** Um módulo novo, `src/graphrag_bulas/retrieval.py`, com três funções públicas: `buscar_seeds` → `expandir` → `recuperar`. Só Cypher de leitura (`routing_="r"`) sobre os índices que já existem em `cypher/schema.cypher`. Sem LLM, sem APOC, sem GDS.

**Tech Stack:** Python 3, driver `neo4j` 5, Neo4j 5 (índices vector e fulltext), `embed()` bge-m3 de `graphrag_bulas.embeddings`, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-28-e5-retrieval-seeds-expansao-design.md`

**Status de validação:** o código final deste plano já rodou uma vez contra o grafo semente em 2026-10-28 (14/14 testes de `tests/test_retrieval.py` e 23/23 na suíte toda, ruff limpo). Se um teste falhar, investigue o grafo/ambiente antes de mudar a lógica.

## Global Constraints

- Branch: `e5/retrieval-seeds-expansao` (já criada, com a spec commitada).
- Commits em pt-BR, semânticos (`feat:`, `test:`, `docs:`), **sem** linha `Co-Authored-By` nem assinatura do Claude.
- Lint: `uv run ruff check .` e `uv run ruff format --check .` limpos (linha máx. 100).
- Testes com Neo4j usam a fixture `db` de `tests/conftest.py`: pulam sem Neo4j ou sem grafo semente.
- Antes dos testes: Docker ligado e `docker compose up -d`; o semente e os embeddings já estão no banco (ver README). Rodar tudo com `uv run`.
- Só leitura no Neo4j: toda consulta passa por `_ler()` (`routing_="r"`).
- Constantes da spec: `MIN_SCORE_VETOR = 0.75`, `MIN_LETRAS_TERMO = 4`, `TOP_VETOR = 10`, `TOP_FULLTEXT = 10`, `k_chunks = 5`, `saltos = 2`, `max_nos = 60`.
- Relações de domínio percorridas: `CONTEM`, `PERTENCE_A`, `INTERAGE_COM`, `INDICADO_PARA`, `CONTRAINDICADO_EM`, `PODE_CAUSAR`, `FABRICADO_POR`. Nunca `MENCIONA`, `DESCREVE`, `TEM_SECAO`, `TEM_CHUNK`.

## File Structure

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `src/graphrag_bulas/retrieval.py` | criar | seeds, expansão, `recuperar` |
| `tests/test_retrieval.py` | criar | 14 testes (1 unitário puro, 13 com o semente) |
| `README.md` | modificar | uma linha de uso do retrieval |

---

### Task 1: Esqueleto do módulo e termos do fulltext

**Files:**
- Create: `src/graphrag_bulas/retrieval.py`
- Test: `tests/test_retrieval.py`

**Interfaces:**
- Consumes: nada.
- Produces: `termos_fulltext(pergunta: str) -> str`; `_ler(driver, cypher: str, **params) -> list[Record]`; constantes `MIN_SCORE_VETOR`, `MIN_LETRAS_TERMO`, `TOP_VETOR`, `TOP_FULLTEXT`, `RELACOES_DOMINIO: list[str]`.

- [ ] **Step 1: Write the failing test** — criar `tests/test_retrieval.py`:

```python
"""Retrieval E5.1 + E5.2 sobre o grafo semente. Pula sem Neo4j (fixture db em conftest.py)."""
from graphrag_bulas.retrieval import termos_fulltext


def test_termos_fulltext_ignora_palavras_curtas_e_especiais():
    assert (
        termos_fulltext('Posso tomar "Marevan" (com) Advil? AND/OR:') == "Posso tomar Marevan Advil"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_retrieval.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'graphrag_bulas.retrieval'`

- [ ] **Step 3: Write minimal implementation** — criar `src/graphrag_bulas/retrieval.py`:

```python
"""Retrieval do GraphRAG (E5.1 + E5.2): seeds híbridas e expansão multi-hop. Só leitura.

Spec: docs/superpowers/specs/2026-10-28-e5-retrieval-seeds-expansao-design.md
"""

import re

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
```

Por que não há escape de Lucene: `\w+` só devolve letras, dígitos e `_`, então nenhum caractere especial chega ao Lucene; e `AND`/`OR`/`NOT` têm menos de 4 letras.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_retrieval.py -v && uv run ruff check . && uv run ruff format --check .`
Expected: 1 passed; ruff limpo.

- [ ] **Step 5: Commit**

```bash
git add src/graphrag_bulas/retrieval.py tests/test_retrieval.py
git commit -m "feat: adiciona módulo de retrieval com termos para o fulltext (E5.1)"
```

---

### Task 2: `buscar_seeds` — seeds híbridas (E5.1)

**Files:**
- Modify: `src/graphrag_bulas/retrieval.py` (import + duas funções no fim)
- Test: `tests/test_retrieval.py`

**Interfaces:**
- Consumes: `_ler`, `termos_fulltext`, constantes (Task 1); `embed(textos: list[str]) -> list[list[float]]` de `graphrag_bulas.embeddings`.
- Produces: `buscar_seeds(driver, pergunta: str, k_chunks: int = 5) -> dict` com
  `{"entidades": [{"id", "nome", "labels": list[str], "fontes": list["vetor"|"fulltext"], "score_vetor": float|None, "score_fulltext": float|None}], "chunks": [{"chunk_id", "texto", "fonte", "score": float}]}`.
  `entidades` ordenadas: nas duas fontes primeiro, depois maior `score_vetor`, depois `id`. `chunks` por `score` decrescente. `fonte` = `id` da `Bula`.

- [ ] **Step 1: Write the failing tests** — em `tests/test_retrieval.py`, trocar a linha de import por

```python
from graphrag_bulas.retrieval import buscar_seeds, termos_fulltext

MAREVAN_ADVIL = "Posso tomar Marevan com Advil?"


def ids_seeds(db, pergunta):
    return {s["id"] for s in buscar_seeds(db, pergunta)["entidades"]}
```

(as duas linhas em branco antes de `def test_termos...` continuam) e acrescentar no fim do arquivo:

```python
def test_seeds_marevan_advil_sem_ruido_vetorial(db):
    seeds = ids_seeds(db, MAREVAN_ADVIL)
    assert {"marevan", "advil"} <= seeds
    assert "enalapril" not in seeds  # vetor 0.70, abaixo do corte


def test_seed_aine_vem_do_fulltext(db):
    ents = {s["id"]: s for s in buscar_seeds(db, "Varfarina interage com algum AINE?")["entidades"]}
    assert "varfarina" in ents
    assert "fulltext" in ents["aine"]["fontes"]


def test_seeds_gravidez(db):
    seeds = ids_seeds(db, "Quais anti-hipertensivos são contraindicados na gravidez?")
    assert {"anti_hipertensivo", "gestante"} <= seeds


def test_chunks_seed_ordenados_e_com_fonte(db):
    chunks = buscar_seeds(db, MAREVAN_ADVIL, k_chunks=3)["chunks"]
    assert len(chunks) == 3
    assert [c["score"] for c in chunks] == sorted((c["score"] for c in chunks), reverse=True)
    assert all(c["fonte"].startswith("bula_") for c in chunks)


def test_pergunta_sem_palavras_nao_consulta(db):
    assert buscar_seeds(db, " ?! ") == {"entidades": [], "chunks": []}


def test_caracteres_especiais_do_lucene_nao_quebram(db):
    seeds = ids_seeds(db, 'Marevan "AND" (Advil) : / ~ * [AINE]?')
    assert {"marevan", "advil"} <= seeds
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_retrieval.py -v`
Expected: FAIL com `ImportError: cannot import name 'buscar_seeds'`

- [ ] **Step 3: Write minimal implementation** — em `src/graphrag_bulas/retrieval.py`, depois de `import re` e de uma linha em branco, acrescentar:

```python
from graphrag_bulas.embeddings import embed
```

e no fim do arquivo:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_retrieval.py -v && uv run ruff check . && uv run ruff format --check .`
Expected: 7 passed; ruff limpo. (Primeira execução baixa/carrega o bge-m3; pode levar ~10 s.)

- [ ] **Step 5: Commit**

```bash
git add src/graphrag_bulas/retrieval.py tests/test_retrieval.py
git commit -m "feat: adiciona buscar_seeds com entidades por vetor e fulltext e chunks por vetor (E5.1)"
```

---

### Task 3: `expandir` e `recuperar` — subgrafo multi-hop e trechos (E5.2)

**Files:**
- Modify: `src/graphrag_bulas/retrieval.py` (duas funções no fim)
- Modify: `README.md`
- Test: `tests/test_retrieval.py`

**Interfaces:**
- Consumes: `buscar_seeds` e seu dict de retorno (Task 2), `_ler`, `RELACOES_DOMINIO`.
- Produces (usado pela parte 2 do E5):
  - `expandir(driver, seeds: dict, saltos: int = 2, max_nos: int = 60) -> dict`
  - `recuperar(driver, pergunta: str) -> dict`
  - Retorno: `{"seeds": list[str], "subgrafo": {"nos": [{"id", "nome", "labels", "dist": int}], "arestas": [{"origem", "destino", "tipo", "props": dict}]}, "trechos": [{"chunk_id", "texto", "fonte", "score": float|None}]}`.
  - `nos` ordenados por `dist`, depois `id`; seeds têm `dist = 0`. `arestas` só entre nós mantidos, direção gravada no grafo. `trechos`: primeiro os citados em `fonte_chunk_id` (`score = None`), depois os chunks-seed; sem `chunk_id` repetido.

- [ ] **Step 1: Write the failing tests** — em `tests/test_retrieval.py`, trocar a linha de import por

```python
from graphrag_bulas.retrieval import buscar_seeds, expandir, recuperar, termos_fulltext
```

e acrescentar no fim do arquivo:

```python
def test_caminho_marevan_advil(db):
    r = recuperar(db, MAREVAN_ADVIL)
    arestas = {(a["origem"], a["destino"], a["tipo"]) for a in r["subgrafo"]["arestas"]}
    assert ("varfarina", "aine", "INTERAGE_COM") in arestas
    assert ("ibuprofeno", "anticoagulante", "INTERAGE_COM") in arestas
    citados = [t["chunk_id"] for t in r["trechos"] if t["score"] is None]
    assert {"bula_marevan_interacoes_0", "bula_advil_interacoes_1"} <= set(citados)


def test_trechos_citados_antes_dos_chunks_seed(db):
    trechos = recuperar(db, MAREVAN_ADVIL)["trechos"]
    scores = [t["score"] for t in trechos]
    n_citados = scores.count(None)
    assert n_citados > 0
    assert all(s is None for s in scores[:n_citados])
    assert len({t["chunk_id"] for t in trechos}) == len(trechos)


def test_gravidez_cozaar_contraindicado(db):
    arestas = recuperar(db, "Quais anti-hipertensivos são contraindicados na gravidez?")[
        "subgrafo"
    ]["arestas"]
    assert any(
        a["origem"] == "cozaar" and a["destino"] == "gestante" and a["tipo"] == "CONTRAINDICADO_EM"
        for a in arestas
    )


def test_efeitos_comuns_losartana_enalapril(db):
    sub = recuperar(db, "Que efeitos losartana e enalapril têm em comum?")["subgrafo"]

    def efeitos(med):
        return {
            a["destino"]
            for a in sub["arestas"]
            if a["origem"] == med and a["tipo"] == "PODE_CAUSAR"
        }

    assert efeitos("cozaar") & efeitos("renitec")


def test_max_nos_mantem_seeds(db):
    seeds = buscar_seeds(db, MAREVAN_ADVIL)
    nos = expandir(db, seeds, max_nos=5)["subgrafo"]["nos"]
    assert len(nos) <= 5
    assert set(expandir(db, seeds, max_nos=5)["seeds"]) <= {n["id"] for n in nos}
    assert all(n["dist"] == 0 for n in nos if n["id"] in {"marevan", "advil"})


def test_nao_percorre_relacoes_de_documento(db):
    labels = {lb for n in recuperar(db, MAREVAN_ADVIL)["subgrafo"]["nos"] for lb in n["labels"]}
    assert not labels & {"Bula", "Secao", "Chunk"}


def test_so_leitura(db):
    def contagem():
        q = "MATCH (n) WITH count(n) AS n MATCH ()-[r]->() RETURN n, count(r) AS r"
        return dict(db.execute_query(q).records[0])

    antes = contagem()
    recuperar(db, MAREVAN_ADVIL)
    assert contagem() == antes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_retrieval.py -v`
Expected: FAIL com `ImportError: cannot import name 'expandir'`

- [ ] **Step 3: Write minimal implementation** — acrescentar no fim de `src/graphrag_bulas/retrieval.py`:

```python
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
```

Notas:
- `*1..{int(saltos)}` entra por f-string porque o Cypher não aceita parâmetro em comprimento de caminho; o `int()` impede injeção.
- `elementId` separa nós com o mesmo `id` em labels diferentes (ex.: `cefaleia` é `Condicao` e `EfeitoAdverso`).
- Tamanho real no semente: 22–51 nós por pergunta-alvo, abaixo de `max_nos = 60`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check . && uv run ruff format --check .`
Expected: `tests/test_retrieval.py` 14 passed; suíte toda 23 passed; ruff limpo.

- [ ] **Step 5: Documentar uso no README** — na seção de grafo semente/embeddings do `README.md`, depois do passo de `embed_missing`, acrescentar:

```markdown
Retrieval do GraphRAG (E5.1 + E5.2), pergunta → seeds → subgrafo + trechos:

    uv run python -c "from graphrag_bulas.config import get_driver; from graphrag_bulas.retrieval import recuperar; import json; print(json.dumps(recuperar(get_driver(), 'Posso tomar Marevan com Advil?'), ensure_ascii=False, indent=2))"
```

- [ ] **Step 6: Commit**

```bash
git add src/graphrag_bulas/retrieval.py tests/test_retrieval.py README.md
git commit -m "feat: adiciona expansão multi-hop por relações de domínio e trechos citados (E5.2)"
```

---

### Task 4: Fechar a parte 1

- [ ] **Step 1:** Marcar E5.1 e E5.2 como feitos onde o time acompanha o plano (`planejamento/PLANO_EQUIPE.md` não tem coluna de status; não editar a tabela). Avisar P5/P6 que o formato de `recuperar()` está na spec.
- [ ] **Step 2:** Rodar `uv run pytest -q` uma última vez e pedir ao usuário o push / merge da branch `e5/retrieval-seeds-expansao` (o usuário faz o push).
- [ ] **Step 3:** Próximo: brainstorming da parte 2 (E5.4 GDS + E5.5 montador de contexto), consumindo `recuperar()`.
