# E5.5 + E5.6 + E5.7 — Contexto, geração e `responder` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Da pergunta à resposta citada: o montador de contexto transforma o retorno de `recuperar` em texto de prompt, a geração pede ao LLM uma resposta com citações e calcula confiança/recusa, e `responder(pergunta, modo)` devolve o contrato JSON da UI e do E7.

**Architecture:** Três módulos novos e pequenos. `contexto.py` (E5.5) é uma função pura sobre o dict de `recuperar`. `geracao.py` (E5.6) só conhece o contexto montado, não o grafo, para o modo `rag` (E5.8) reusar. `api.py` (E5.7) liga `recuperar` → `montar_contexto` → `gerar_resposta`.

**Tech Stack:** Python 3.12, LangChain `with_structured_output` + pydantic (`Literal`), Gemini via `get_llm()`, driver `neo4j` 6.x (só via `recuperar`), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-28-e5-contexto-geracao-api-design.md`

**Status de validação:** o código final deste plano rodou em 2026-10-28 contra o grafo semente, fora dos commits: testes de `contexto`, `geracao` e `api` passando, ruff limpo. Se um teste falhar, investigue o ambiente antes de mudar a lógica.

## Global Constraints

- Branch: `e5/contexto-geracao` (spec já commitada na `main`, que é a base desta branch).
- Commits em pt-BR, semânticos (`feat:`, `test:`, `docs:`), **sem** linha `Co-Authored-By` nem assinatura do Claude.
- Lint: `uv run ruff check .` limpo e `uv run ruff format --check src tests` limpo (linha máx. 100). O `ruff format --check .` do repo inteiro falha num `.md` antigo de `docs/superpowers/plans/`; não mexa nele.
- Testes com Neo4j usam a fixture `db` de `tests/conftest.py`: pulam sem Neo4j ou sem grafo semente. Antes: Docker ligado e `docker compose up -d`. Rodar tudo com `uv run`.
- `tests/` não tem `__init__.py`: o pytest põe a pasta no `sys.path`, então `from test_geracao import ...` funciona.
- Constantes da spec: `max_fatos=100`, `max_trechos=20`, `PESO_SUPORTE = {"total": 1.0, "parcial": 0.6, "nenhum": 0.0}`, `RECUSA = "Não encontrei nas bulas informação suficiente para responder com segurança."`.
- Props internas fora do texto dos fatos: `fonte_chunk_id`, `confianca`, `metodo`.
- `gerar_resposta` deixa a exceção do LLM propagar (diferente de `consultar`, que nunca levanta).
- Contrato de `responder`: chaves exatamente `modo, resposta, subgrafo, cypher, nos, confianca, recusou, trechos`; cada trecho ganha `citado: bool`.
- Quem chama passa o LLM com `temperature=0`; `responder` usa `get_llm(temperature=0)` quando `llm=None`.

## File Structure

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `src/graphrag_bulas/contexto.py` | criar | E5.5: `montar_contexto(r, max_fatos=100, max_trechos=20)` |
| `tests/test_contexto.py` | criar | 7 testes: 6 sem Neo4j, 1 com o semente |
| `src/graphrag_bulas/geracao.py` | criar | E5.6: `Resposta`, `RECUSA`, `NOTA_SEM_CONSULTA`, `gerar_resposta` |
| `tests/test_geracao.py` | criar | 8 testes sem Neo4j; `LLMFalso` com fila por schema |
| `src/graphrag_bulas/api.py` | criar | E5.7: `responder(pergunta, modo="graphrag", driver=None, llm=None)` |
| `tests/test_api.py` | criar | 5 testes: 2 com o semente, 2 sem Neo4j, 1 com o Gemini real (opcional) |
| `README.md` | modificar (depois do bloco do retrieval, linhas 35–38) | exemplo de `responder` |

---

### Task 1: Montador de contexto (E5.5)

**Files:**
- Create: `src/graphrag_bulas/contexto.py`
- Test: `tests/test_contexto.py`

**Interfaces:**
- Consumes: o dict de `recuperar(driver, pergunta, llm=None)` (`src/graphrag_bulas/retrieval.py`): `{"seeds": [str], "subgrafo": {"nos": [{"id", "nome", "labels", "dist"}], "arestas": [{"origem", "destino", "tipo", "props": dict}]}, "trechos": [{"chunk_id", "texto", "fonte", "score": float | None}], "cypher": None | {"query", "linhas": [dict], "erro": str | None}}`.
- Produces: `montar_contexto(r, max_fatos=100, max_trechos=20) -> {"texto": str, "chunk_ids": set[str], "nos": set[str], "trechos": list[dict], "sem_consulta": bool}`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_contexto.py`:

```python
"""Montador de contexto (E5.5). Função pura: r montado à mão, sem Neo4j."""

from graphrag_bulas.contexto import montar_contexto


def aresta(origem, tipo, destino, fonte=None, confianca=1.0, **props):
    p = {"confianca": confianca, "metodo": "manual", **props}
    if fonte:
        p["fonte_chunk_id"] = fonte
    return {"origem": origem, "tipo": tipo, "destino": destino, "props": p}


def trecho(cid, score=None):
    return {"chunk_id": cid, "texto": f"texto de {cid}", "fonte": "bula_x", "score": score}


def r_base(arestas=(), trechos=(), cypher=None):
    nos = [
        {"id": "marevan", "nome": "Marevan", "labels": ["Medicamento"], "dist": 0},
        {"id": "varfarina", "nome": "Varfarina", "labels": ["PrincipioAtivo"], "dist": 1},
        {"id": "aine", "nome": "AINEs", "labels": ["ClasseTerapeutica"], "dist": 2},
    ]
    return {
        "seeds": ["marevan"],
        "subgrafo": {"nos": nos, "arestas": list(arestas)},
        "trechos": list(trechos),
        "cypher": cypher,
    }


def test_fato_tem_nomes_props_fonte_e_ids_sem_props_internas():
    r = r_base([aresta("marevan", "CONTEM", "varfarina", "c1", dose="5 mg")])
    texto = montar_contexto(r)["texto"]
    linha = "- Marevan -[CONTEM {dose: 5 mg}]-> Varfarina [c1] (ids: marevan, varfarina)"
    assert linha in texto
    assert "confianca" not in texto and "metodo" not in texto and "fonte_chunk_id" not in texto


def test_fatos_ordenados_por_dist_e_confianca_e_cortados():
    r = r_base(
        [
            aresta("varfarina", "INTERAGE_COM", "aine", "c3"),  # dist 1
            aresta("marevan", "PODE_CAUSAR", "x", "c2", confianca=0.5),  # dist 0
            aresta("marevan", "CONTEM", "varfarina", "c1", confianca=0.9),  # dist 0
        ]
    )
    ctx = montar_contexto(r, max_fatos=2)
    assert ctx["texto"].index("CONTEM") < ctx["texto"].index("PODE_CAUSAR")
    assert "INTERAGE_COM" not in ctx["texto"]
    assert ctx["nos"] == {"marevan", "varfarina", "x"}
    assert ctx["chunk_ids"] == {"c1", "c2"}


def test_trechos_citados_pelos_fatos_vem_primeiro_e_sao_cortados():
    r = r_base(
        [aresta("marevan", "CONTEM", "varfarina", "c1")],
        [trecho("s1", 0.9), trecho("s2", 0.8), trecho("c1"), trecho("s3", None)],
    )
    ctx = montar_contexto(r, max_trechos=3)
    assert [t["chunk_id"] for t in ctx["trechos"]] == ["c1", "s1", "s2"]
    assert ctx["texto"].index("[c1] (bula_x) texto de c1") < ctx["texto"].index("[s1]")


def test_linhas_do_cypher_entram_so_sem_erro():
    linha = {"medicamento": "Advil", "fonte_chunk_id": "c9"}
    ok = montar_contexto(r_base(cypher={"query": "q", "linhas": [linha], "erro": None}))
    assert '- {"fonte_chunk_id": "c9", "medicamento": "Advil"}' in ok["texto"]
    assert "c9" in ok["chunk_ids"]
    erro = montar_contexto(r_base(cypher={"query": "q", "linhas": [linha], "erro": "x"}))
    assert "Cypher" not in erro["texto"]


def test_sem_consulta():
    r = r_base(cypher={"query": None, "linhas": [], "erro": "sem_consulta"})
    assert montar_contexto(r)["sem_consulta"] is True
    assert montar_contexto(r_base())["sem_consulta"] is False


def test_contexto_vazio():
    ctx = montar_contexto(r_base())
    assert ctx["texto"] == "" and ctx["chunk_ids"] == set() and ctx["nos"] == set()


def test_contexto_do_semente_traz_a_interacao_marevan_advil(db):
    # Guarda dos limites: se o grafo crescer (M2) e a interação sair do contexto, reveja o corte.
    from graphrag_bulas.retrieval import recuperar

    ctx = montar_contexto(recuperar(db, "Posso tomar Marevan com Advil?"))
    assert {"bula_marevan_interacoes_0", "bula_advil_interacoes_1"} <= ctx["chunk_ids"]
    assert "- Varfarina -[INTERAGE_COM" in ctx["texto"]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_contexto.py -v`
Expected: erro de coleta `ModuleNotFoundError: No module named 'graphrag_bulas.contexto'`.

- [ ] **Step 3: Implementar**

Criar `src/graphrag_bulas/contexto.py`:

```python
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
                "- " + json.dumps(linha, ensure_ascii=False, sort_keys=True) for linha in linhas
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
        | {linha["fonte_chunk_id"] for linha in linhas if linha.get("fonte_chunk_id")},
        "nos": {a["origem"] for a in arestas} | {a["destino"] for a in arestas},
        "trechos": trechos,
        "sem_consulta": cypher.get("erro") == "sem_consulta",
    }
```

Notas:
- `dist` 99 para id fora de `subgrafo.nos` (não deveria acontecer; a aresta só vem entre nós do subgrafo).
- Trechos: os citados pelos fatos que entraram vêm primeiro, na ordem dos fatos; depois os outros por `score` decrescente, `None` por último. `setdefault` tira `chunk_id` repetido mantendo a primeira ocorrência.
- O teste com `db` carrega o bge-m3 (via `recuperar`); a primeira execução pode levar minutos.

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_contexto.py -v`
Expected: 7 passed.

- [ ] **Step 5: Lint e commit**

```bash
uv run ruff check . && uv run ruff format --check src tests
git add src/graphrag_bulas/contexto.py tests/test_contexto.py
git commit -m "feat: adiciona montador de contexto ordenado por distância (E5.5)"
```

---

### Task 2: Geração com citação, recusa e confiança (E5.6)

**Files:**
- Create: `src/graphrag_bulas/geracao.py`
- Test: `tests/test_geracao.py`

**Interfaces:**
- Consumes: o dict de `montar_contexto` (Task 1): usa `texto`, `chunk_ids`, `nos`, `sem_consulta`.
- Produces: `class Resposta(BaseModel)` (`resposta: str`, `chunks: list[str]`, `nos: list[str]`, `suporte: Literal["total", "parcial", "nenhum"]`); constantes `PESO_SUPORTE`, `RECUSA`, `NOTA_SEM_CONSULTA`, `REGRAS`; `gerar_resposta(llm, pergunta, contexto) -> {"resposta": str, "chunks": list[str], "nos": list[str], "confianca": float, "recusou": bool}`. No teste: `class LLMFalso(**filas)` (uma fila por nome de schema, ex. `Resposta=[...]`, `Consulta=[...]`) e `resp(...)`, usados pela Task 3.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_geracao.py`:

```python
"""Geração da resposta (E5.6). LLM falso, sem Neo4j."""

import pytest

from graphrag_bulas.geracao import NOTA_SEM_CONSULTA, RECUSA, Resposta, gerar_resposta

CTX = {
    "texto": "Fatos do grafo:\n- Marevan -[CONTEM]-> Varfarina [c1] (ids: marevan, varfarina)",
    "chunk_ids": {"c1", "c2"},
    "nos": {"marevan", "varfarina"},
    "trechos": [],
    "sem_consulta": False,
}
VAZIO = {**CTX, "texto": "", "chunk_ids": set(), "nos": set()}


class LLMFalso:
    """Uma fila de respostas por schema (str do nome da classe); Exception é levantada."""

    def __init__(self, **filas):
        self.filas = {k: list(v) for k, v in filas.items()}
        self.prompts = []
        self._schema = None

    def with_structured_output(self, schema):
        self._schema = schema.__name__
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        r = self.filas[self._schema].pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def resp(chunks=("c1",), nos=("marevan",), suporte="total", resposta="Sim."):
    return Resposta(resposta=resposta, chunks=list(chunks), nos=list(nos), suporte=suporte)


def test_resposta_feliz():
    llm = LLMFalso(Resposta=[resp()])
    g = gerar_resposta(llm, "Marevan tem varfarina?", CTX)
    assert g == {
        "resposta": "Sim.",
        "chunks": ["c1"],
        "nos": ["marevan"],
        "confianca": 1.0,
        "recusou": False,
    }
    assert CTX["texto"] in llm.prompts[0] and "Marevan tem varfarina?" in llm.prompts[0]
    assert NOTA_SEM_CONSULTA not in llm.prompts[0]


def test_citacao_inventada_descartada_e_confianca_reduzida():
    llm = LLMFalso(
        Resposta=[resp(chunks=["c1", "inventado"], nos=["marevan", "x"], suporte="parcial")]
    )
    g = gerar_resposta(llm, "p", CTX)
    assert g["chunks"] == ["c1"] and g["nos"] == ["marevan"]
    assert g["confianca"] == 0.3  # 0.6 * 2/4


@pytest.mark.parametrize("r", [resp(suporte="nenhum"), resp(chunks=["inventado"]), resp(chunks=[])])
def test_recusa_sem_suporte_ou_sem_chunk_valido(r):
    g = gerar_resposta(LLMFalso(Resposta=[r]), "p", CTX)
    assert g == {"resposta": RECUSA, "chunks": [], "nos": [], "confianca": 0.0, "recusou": True}


def test_contexto_vazio_recusa_sem_chamar_llm():
    llm = LLMFalso(Resposta=[])
    assert gerar_resposta(llm, "p", VAZIO)["recusou"] is True
    assert llm.prompts == []


def test_nota_sem_consulta_no_prompt():
    llm = LLMFalso(Resposta=[resp()])
    gerar_resposta(llm, "p", {**CTX, "sem_consulta": True})
    assert NOTA_SEM_CONSULTA in llm.prompts[0]


def test_falha_do_llm_propaga():
    with pytest.raises(RuntimeError, match="cota"):
        gerar_resposta(LLMFalso(Resposta=[RuntimeError("cota")]), "p", CTX)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_geracao.py -v`
Expected: erro de coleta `ModuleNotFoundError: No module named 'graphrag_bulas.geracao'`.

- [ ] **Step 3: Implementar**

Criar `src/graphrag_bulas/geracao.py`:

```python
"""Geração da resposta (E5.6): cita o contexto, recusa sem suporte e calcula a confiança.

Spec: docs/superpowers/specs/2026-10-28-e5-contexto-geracao-api-design.md
"""

from typing import Literal

from pydantic import BaseModel, Field

PESO_SUPORTE = {"total": 1.0, "parcial": 0.6, "nenhum": 0.0}
RECUSA = "Não encontrei nas bulas informação suficiente para responder com segurança."

REGRAS = """Você responde perguntas sobre bulas de medicamentos.

Regras:
- Responda em português, só com o contexto abaixo, sem conhecimento próprio.
- Em chunks, liste os chunk_ids (entre colchetes no contexto) que sustentam a resposta. Em nos,
  liste os ids das entidades usadas (os ids aparecem em "ids:" nos fatos).
- suporte: total se o contexto sustenta toda a resposta, parcial se sustenta só parte, nenhum se
  não sustenta.
- Em pergunta sobre interação, contraindicação ou dose, oriente procurar médico ou farmacêutico."""

NOTA_SEM_CONSULTA = "A consulta estruturada indicou que o schema do grafo não cobre esta pergunta."


class Resposta(BaseModel):
    resposta: str
    chunks: list[str] = Field(description="chunk_ids que sustentam a resposta")
    nos: list[str] = Field(description="ids das entidades usadas")
    suporte: Literal["total", "parcial", "nenhum"]


def _recusa():
    return {"resposta": RECUSA, "chunks": [], "nos": [], "confianca": 0.0, "recusou": True}


def gerar_resposta(llm, pergunta, contexto):
    """Pede a Resposta ao LLM e confere as citações. Falha do LLM propaga."""
    if not contexto["texto"]:
        return _recusa()
    partes = [REGRAS]
    if contexto["sem_consulta"]:
        partes.append(NOTA_SEM_CONSULTA)
    partes += ["Contexto:\n" + contexto["texto"], f"Pergunta: {pergunta}"]
    r = llm.with_structured_output(Resposta).invoke("\n\n".join(partes))
    chunks = [c for c in dict.fromkeys(r.chunks) if c in contexto["chunk_ids"]]
    nos = [n for n in dict.fromkeys(r.nos) if n in contexto["nos"]]
    if r.suporte == "nenhum" or not chunks:
        return _recusa()
    citadas = len(set(r.chunks)) + len(set(r.nos))
    confianca = round(PESO_SUPORTE[r.suporte] * (len(chunks) + len(nos)) / citadas, 2)
    return {
        "resposta": r.resposta,
        "chunks": chunks,
        "nos": nos,
        "confianca": confianca,
        "recusou": False,
    }
```

Notas:
- Confiança: `PESO_SUPORTE[suporte] × válidas / citadas`, contando chunks e nós sem repetição. Ex.: `parcial`, 2 de 4 citações válidas → `0.6 × 2/4 = 0.3`.
- Recusa quando `suporte == "nenhum"` ou nenhum chunk válido; contexto vazio recusa sem chamar o LLM.
- Concatenação e não `str.format`: o contexto tem `{...}` das props.

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_geracao.py -v`
Expected: 8 passed.

- [ ] **Step 5: Lint e commit**

```bash
uv run ruff check . && uv run ruff format --check src tests
git add src/graphrag_bulas/geracao.py tests/test_geracao.py
git commit -m "feat: adiciona geração com citações conferidas, recusa e confiança (E5.6)"
```

---

### Task 3: `responder`, teste com Gemini real e README (E5.7)

**Files:**
- Create: `src/graphrag_bulas/api.py`
- Test: `tests/test_api.py`
- Modify: `README.md` (depois da linha 38, o comando do retrieval)

**Interfaces:**
- Consumes: `recuperar(driver, pergunta, llm=None)` (E5.1–E5.3), `montar_contexto` (Task 1), `gerar_resposta` (Task 2), `get_driver`, `get_llm` (`config.py`), `Consulta` (`text2cypher.py`); no teste, `LLMFalso` e `resp` de `tests/test_geracao.py`.
- Produces: `responder(pergunta, modo="graphrag", driver=None, llm=None) -> dict` com as chaves `modo, resposta, subgrafo, cypher, nos, confianca, recusou, trechos`. `modo="rag"` levanta `NotImplementedError("modo rag: E5.8")`; outro modo levanta `ValueError("modo desconhecido: ...")`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_api.py`:

```python
"""API responder (E5.7) no grafo semente. LLM falso; Gemini real com GRAPHRAG_TESTAR_LLM=1."""

import os

import pytest
from test_geracao import LLMFalso, resp

from graphrag_bulas.api import responder
from graphrag_bulas.text2cypher import Consulta

MAREVAN_ADVIL = "Posso tomar Marevan com Advil?"
INTERACAO = (
    "MATCH (:Medicamento {id: 'marevan'})-[:CONTEM]->(:PrincipioAtivo)-[r:INTERAGE_COM]-(x) "
    "RETURN x.nome AS com, r.efeito AS efeito, r.fonte_chunk_id AS fonte_chunk_id LIMIT 50"
)
CHAVES = {"modo", "resposta", "subgrafo", "cypher", "nos", "confianca", "recusou", "trechos"}


def test_responder_monta_o_contrato(db):
    llm = LLMFalso(
        Consulta=[Consulta(cypher=INTERACAO)],
        Resposta=[resp(chunks=["bula_marevan_interacoes_0"], nos=["varfarina"])],
    )
    r = responder(MAREVAN_ADVIL, driver=db, llm=llm)
    assert set(r) == CHAVES
    assert r["modo"] == "graphrag" and r["recusou"] is False and r["confianca"] == 1.0
    assert r["cypher"] == INTERACAO
    assert r["nos"] == ["varfarina"] and r["subgrafo"]["arestas"]
    citados = [t["chunk_id"] for t in r["trechos"] if t["citado"]]
    assert citados == ["bula_marevan_interacoes_0"]


def test_responder_sem_cypher_e_com_recusa(db):
    llm = LLMFalso(Consulta=[Consulta(cypher="")], Resposta=[resp(suporte="nenhum")])
    r = responder("Qual a cor do comprimido de Cozaar?", driver=db, llm=llm)
    assert r["cypher"] is None and r["recusou"] is True and r["confianca"] == 0.0
    assert not any(t["citado"] for t in r["trechos"])
    assert "não cobre" in llm.prompts[-1]  # sem_consulta chegou à geração


def test_modo_rag_ainda_nao_existe():
    with pytest.raises(NotImplementedError, match="E5.8"):
        responder("x", modo="rag")


def test_modo_invalido():
    with pytest.raises(ValueError, match="modo desconhecido"):
        responder("x", modo="kag")


@pytest.mark.skipif(
    os.getenv("GRAPHRAG_TESTAR_LLM") != "1",
    reason="Gemini real: defina GRAPHRAG_TESTAR_LLM=1 (gasta cota, não determinístico)",
)
def test_gemini_real_responde_e_recusa(db):
    from graphrag_bulas.config import get_llm

    llm = get_llm(temperature=0)
    ok = responder(MAREVAN_ADVIL, driver=db, llm=llm)
    assert not ok["recusou"] and any(t["citado"] for t in ok["trechos"]), ok
    nao = responder("Qual a cor do comprimido de Cozaar?", driver=db, llm=llm)
    assert nao["recusou"], nao
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_api.py -v`
Expected: erro de coleta `ModuleNotFoundError: No module named 'graphrag_bulas.api'`.

- [ ] **Step 3: Implementar**

Criar `src/graphrag_bulas/api.py`:

```python
"""API única (E5.7): responder(pergunta, modo) -> contrato JSON da UI e do E7.

Spec: docs/superpowers/specs/2026-10-28-e5-contexto-geracao-api-design.md
"""

from graphrag_bulas.config import get_driver, get_llm
from graphrag_bulas.contexto import montar_contexto
from graphrag_bulas.geracao import gerar_resposta
from graphrag_bulas.retrieval import recuperar


def responder(pergunta, modo="graphrag", driver=None, llm=None):
    """Pergunta -> resposta citada. modo "rag" chega no E5.8."""
    if modo == "rag":
        raise NotImplementedError("modo rag: E5.8")
    if modo != "graphrag":
        raise ValueError(f"modo desconhecido: {modo}")
    llm = llm or get_llm(temperature=0)
    if driver is None:
        with get_driver() as d:
            return responder(pergunta, modo, d, llm)
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

Notas:
- O mesmo `llm` serve ao Text-to-Cypher (dentro de `recuperar`) e à geração; por isso o `LLMFalso` da Task 2 tem uma fila por schema.
- `driver=None`: abre um driver só para esta chamada e fecha no fim (`with`). UI e E7 passam o próprio driver.
- `modo` é checado antes de criar LLM ou driver: os testes de modo rodam sem Neo4j e sem cota.

No `README.md`, depois da linha 38 (o comando `uv run python -c "... recuperar ..."`), acrescentar uma linha em branco e:

```markdown
Resposta completa (E5.5 + E5.6 + E5.7), com citações, confiança e recusa:

    uv run python -c "from graphrag_bulas.api import responder; import json; print(json.dumps(responder('Posso tomar Marevan com Advil?'), ensure_ascii=False, indent=2))"
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest -v`
Expected: suíte toda passa; `test_gemini_real_responde_e_recusa` (e o do E5.3) aparecem como skipped.

Depois, uma vez, com o Gemini real:

Run: `GRAPHRAG_TESTAR_LLM=1 uv run pytest tests/test_api.py -v -k gemini`
Expected: 1 passed. Se falhar, leia o dict na mensagem de erro: o problema é o prompt, não o código. Pode levar minutos (bge-m3 carrega; o Gemini é chamado 4 vezes).

- [ ] **Step 5: Lint e commit**

```bash
uv run ruff check . && uv run ruff format --check src tests
git add src/graphrag_bulas/api.py tests/test_api.py README.md
git commit -m "feat: adiciona responder com o contrato da API (E5.7)"
```
