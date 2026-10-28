# E5.3 — Text-to-Cypher — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O LLM gera uma consulta Cypher de leitura a partir da pergunta e das seeds do E5.1; o código valida, executa com segurança e devolve as linhas junto com o subgrafo do E5.2.

**Architecture:** Módulo novo `src/graphrag_bulas/text2cypher.py` com `gerar_cypher` (prompt + LLM), `validar_cypher` (regex de palavras proibidas + `EXPLAIN` + `query_type == "r"`) e `consultar` (gera → valida → executa em transação de leitura, 1 nova tentativa, nunca levanta exceção). `recuperar()` em `retrieval.py` ganha `llm=None` e põe o resultado em `r["cypher"]`.

**Tech Stack:** Python 3.12, driver `neo4j` 6.4 (`READ_ACCESS`, `unit_of_work`, `Result.fetch`), LangChain `with_structured_output` + pydantic, Gemini via `get_llm()`, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-28-e5-text2cypher-design.md`

**Status de validação:** o código final deste plano rodou em 2026-10-28 contra o grafo semente, fora do repo: 17/17 testes, incluindo o teste com o Gemini real, que gerou um Cypher certo para "Posso tomar Marevan com Advil?" (2 linhas, `bula_marevan_interacoes_0` e `bula_advil_interacoes_1`). Ruff limpo. Se um teste falhar, investigue o ambiente antes de mudar a lógica.

## Global Constraints

- Branch: `e5/retrieval-impl` (spec já commitada nela).
- Commits em pt-BR, semânticos (`feat:`, `test:`, `docs:`), **sem** linha `Co-Authored-By` nem assinatura do Claude.
- Lint: `uv run ruff check .` e `uv run ruff format --check .` limpos (linha máx. 100).
- **Ordem dos imports:** a pasta `neo4j/` na raiz do repo (dados do Docker) faz o ruff tratar `neo4j` como pacote local. O bloco `from neo4j import ...` vem **depois** de `from pydantic import ...`, separado por linha em branco. Use `uv run ruff check --fix` se o ruff reclamar.
- Testes com Neo4j usam a fixture `db` de `tests/conftest.py`: pulam sem Neo4j ou sem grafo semente.
- Antes dos testes: Docker ligado e `docker compose up -d`; semente e embeddings já no banco. Rodar tudo com `uv run`.
- Constantes da spec: `TIMEOUT_S = 5`, `MAX_LINHAS = 50`, `tentativas = 2`, `SEM_CONSULTA = "sem_consulta"`.
- Palavras proibidas: `CALL`, `LOAD`, `CREATE`, `MERGE`, `SET`, `DELETE`, `DETACH`, `REMOVE`, `DROP`, `FOREACH`, `SHOW`, `TERMINATE`, `USE`, `ALTER`, `GRANT`, `DENY`, `REVOKE`, `START`, `STOP`, `APOC`.
- `consultar` nunca levanta exceção. Retorno sempre `{"query": str | None, "linhas": list[dict], "erro": str | None}`.
- Quem chama passa o LLM com `temperature=0` (ex.: `get_llm(temperature=0)`).

## File Structure

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `src/graphrag_bulas/text2cypher.py` | criar | prompt, geração, validação, execução |
| `tests/test_text2cypher.py` | criar | 20 testes: 10 sem Neo4j, 9 com o semente, 1 com o Gemini real (opcional) |
| `src/graphrag_bulas/retrieval.py` | modificar (`recuperar`, fim do arquivo) | parâmetro `llm=None` e chave `cypher` |
| `tests/test_retrieval.py` | modificar (fim do arquivo) | 2 testes de `recuperar` com e sem LLM |
| `README.md` | modificar (linhas 35–37) | exemplo de uso com LLM |

---

### Task 1: Prompt e `gerar_cypher`

**Files:**
- Create: `src/graphrag_bulas/text2cypher.py`
- Test: `tests/test_text2cypher.py`

**Interfaces:**
- Consumes: nada de tarefas anteriores. `seeds` tem o formato de `buscar_seeds(...)["entidades"]`: `[{"id": str, "nome": str, "labels": [str], ...}]`.
- Produces: `class Consulta(BaseModel): cypher: str`; `gerar_cypher(llm, pergunta, seeds, anterior=None, erro=None) -> str`; constante `IDS_EXEMPLOS: list[str]`. No arquivo de teste: `class LLMFalso`, constantes `SEEDS`, `MAREVAN_ADVIL`, `RUIM`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_text2cypher.py`:

```python
"""Text-to-Cypher (E5.3). LLM falso: determinístico e sem cota. Neo4j via fixture db."""

from graphrag_bulas.text2cypher import IDS_EXEMPLOS, Consulta, gerar_cypher

MAREVAN_ADVIL = "Posso tomar Marevan com Advil?"
SEEDS = [{"id": "marevan", "nome": "Marevan", "labels": ["Medicamento"]}]
RUIM = "MATCH (n RETURN n"


class LLMFalso:
    """Devolve as respostas em ordem (str vira Consulta; Exception é levantada) e guarda prompts."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.prompts = []

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return Consulta(cypher=r)


def test_prompt_tem_seeds_e_pergunta():
    llm = LLMFalso("  MATCH (n) RETURN n.id LIMIT 1  ")
    assert gerar_cypher(llm, MAREVAN_ADVIL, SEEDS) == "MATCH (n) RETURN n.id LIMIT 1"
    assert "marevan (Medicamento): Marevan" in llm.prompts[0]
    assert MAREVAN_ADVIL in llm.prompts[0]
    assert "Erro:" not in llm.prompts[0]


def test_prompt_da_nova_tentativa_tem_cypher_anterior_e_erro():
    llm = LLMFalso("x")
    gerar_cypher(llm, MAREVAN_ADVIL, [], anterior=RUIM, erro="Invalid input 'RETURN'")
    assert "Seeds:\nnenhuma" in llm.prompts[0]
    assert RUIM in llm.prompts[0]
    assert "Invalid input 'RETURN'" in llm.prompts[0]


def test_exemplos_do_prompt_estao_fora_do_grafo(db):
    # Se o corpus (M2) trouxer um desses remédios, troque o exemplo: ele vazaria a resposta.
    q = "MATCH (n:Entidade) WHERE n.id IN $ids RETURN count(n) AS n"
    assert db.execute_query(q, ids=IDS_EXEMPLOS).records[0]["n"] == 0
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_text2cypher.py -v`
Expected: erro de coleta `ModuleNotFoundError: No module named 'graphrag_bulas.text2cypher'`.

- [ ] **Step 3: Implementar**

Criar `src/graphrag_bulas/text2cypher.py`:

```python
"""Text-to-Cypher (E5.3): o LLM gera Cypher de leitura a partir da pergunta e das seeds.

Spec: docs/superpowers/specs/2026-10-28-e5-text2cypher-design.md
"""

from pydantic import BaseModel, Field

REGRAS = """Você traduz perguntas sobre bulas de medicamentos em UMA consulta Cypher para o Neo4j.

Regras:
- Só leitura: use MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY e LIMIT. Nunca use
  CREATE, MERGE, SET, DELETE, REMOVE, DROP, CALL, FOREACH ou LOAD CSV.
- Use só os labels, relações e propriedades do schema abaixo.
- Filtre entidades por id, usando só os ids da lista de seeds. Escreva os ids literais, sem
  parâmetros ($).
- Leia INTERAGE_COM sem direção: (a)-[r:INTERAGE_COM]-(b).
- INTERAGE_COM pode apontar para uma ClasseTerapeutica. Para achar os princípios ativos dessa
  classe, desça por (classe)<-[:PERTENCE_A]-(pa:PrincipioAtivo).
- Ao retornar um fato de uma relação r, retorne também r.fonte_chunk_id.
- Retorne propriedades (m.nome, r.dose), nunca nós inteiros.
- Termine com LIMIT 50.
- Se o schema não responde à pergunta, devolva cypher vazio."""

# Manter em sincronia com docs/modelagem.md, seções 3 e 4.
SCHEMA = """Schema (todo nó abaixo também tem o label :Entidade).

Nós, todos com id, nome e sinonimos:
- Medicamento {registro_anvisa, generico: bool}
- PrincipioAtivo
- ClasseTerapeutica
- Condicao
- EfeitoAdverso
- Fabricante
- Populacao: id só pode ser 'gestante', 'lactante', 'pediatrico' ou 'idoso'

Relações, todas com fonte_chunk_id, confianca e metodo:
- (:Medicamento)-[:CONTEM {dose}]->(:PrincipioAtivo)
- (:PrincipioAtivo)-[:PERTENCE_A]->(:ClasseTerapeutica)
- (:Medicamento)-[:INDICADO_PARA]->(:Condicao)
- (:Medicamento)-[:CONTRAINDICADO_EM]->(:Condicao|Populacao)
- (:Medicamento)-[:PODE_CAUSAR {frequencia}]->(:EfeitoAdverso)
- (:PrincipioAtivo)-[:INTERAGE_COM {gravidade, efeito}]->(:PrincipioAtivo|ClasseTerapeutica)
- (:Medicamento)-[:FABRICADO_POR]->(:Fabricante)

frequencia: muito_comum, comum, incomum, rara, muito_rara, desconhecida.
gravidade: grave, moderada, leve, desconhecida."""

# Remédios fora do grafo semente: não vazam as perguntas-alvo nem o gold set do E7.
EXEMPLOS = """Exemplos:

Pergunta: Quais efeitos raros a Novalgina pode causar?
Seeds: novalgina (Medicamento): Novalgina
Cypher:
MATCH (m:Medicamento {id: 'novalgina'})-[r:PODE_CAUSAR]->(e:EfeitoAdverso)
WHERE r.frequencia IN ['rara', 'muito_rara']
RETURN e.nome AS efeito, r.frequencia AS frequencia, r.fonte_chunk_id AS fonte_chunk_id
LIMIT 50

Pergunta: Qual a dose de omeprazol no Losec?
Seeds: losec (Medicamento): Losec; omeprazol (PrincipioAtivo): Omeprazol
Cypher:
MATCH (m:Medicamento {id: 'losec'})-[r:CONTEM]->(p:PrincipioAtivo {id: 'omeprazol'})
RETURN m.nome AS medicamento, p.nome AS principio_ativo, r.dose AS dose,
       r.fonte_chunk_id AS fonte_chunk_id
LIMIT 50

Pergunta: Algum remédio com dipirona é contraindicado para idosos?
Seeds: dipirona (PrincipioAtivo): Dipirona; idoso (Populacao): Idoso
Cypher:
MATCH (m:Medicamento)-[:CONTEM]->(:PrincipioAtivo {id: 'dipirona'}),
      (m)-[r:CONTRAINDICADO_EM]->(po:Populacao {id: 'idoso'})
RETURN m.nome AS medicamento, po.nome AS populacao, r.fonte_chunk_id AS fonte_chunk_id
LIMIT 50

Pergunta: Qual a cor do comprimido de Losec?
Seeds: losec (Medicamento): Losec
Cypher: (vazio)"""

IDS_EXEMPLOS = ["novalgina", "losec", "omeprazol", "dipirona"]


class Consulta(BaseModel):
    cypher: str = Field(description="Consulta Cypher de leitura, ou vazio se o schema não responde")


def gerar_cypher(llm, pergunta, seeds, anterior=None, erro=None):
    """Monta o prompt e pede ao LLM uma Consulta. Não acessa o Neo4j."""
    linhas = [f"{s['id']} ({', '.join(s['labels'])}): {s['nome']}" for s in seeds]
    partes = [REGRAS, SCHEMA, EXEMPLOS, "Seeds:\n" + ("\n".join(linhas) or "nenhuma")]
    partes.append(f"Pergunta: {pergunta}")
    if erro:
        partes.append(
            f"A consulta anterior falhou. Corrija.\nCypher anterior: {anterior}\nErro: {erro}"
        )
    return llm.with_structured_output(Consulta).invoke("\n\n".join(partes)).cypher.strip()
```

Por que concatenar e não `str.format`: os exemplos de Cypher têm `{id: ...}`, e `format` quebraria.

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_text2cypher.py -v`
Expected: 3 passed (o terceiro pula se o Neo4j estiver desligado).

- [ ] **Step 5: Lint e commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/graphrag_bulas/text2cypher.py tests/test_text2cypher.py
git commit -m "feat: adiciona prompt e gerar_cypher do Text-to-Cypher (E5.3)"
```

---

### Task 2: `validar_cypher` e limpeza de embeddings

**Files:**
- Modify: `src/graphrag_bulas/text2cypher.py`
- Test: `tests/test_text2cypher.py`

**Interfaces:**
- Consumes: módulo da Task 1.
- Produces: `class CypherInvalido(Exception)`; `validar_cypher(driver, cypher) -> None` (levanta `CypherInvalido`; mensagem `SEM_CONSULTA` quando vazio); `_sem_embedding(v)`; constantes `SEM_CONSULTA`, `PROIBIDAS`, `TIMEOUT_S`, `MAX_LINHAS`. No teste: constante `COZAAR`.

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/test_text2cypher.py`, trocar o import do topo por:

```python
import pytest

from graphrag_bulas.text2cypher import (
    IDS_EXEMPLOS,
    SEM_CONSULTA,
    Consulta,
    CypherInvalido,
    _sem_embedding,
    gerar_cypher,
    validar_cypher,
)
```

Depois de `RUIM = ...`, adicionar:

```python
COZAAR = (
    "MATCH (m:Medicamento {id: 'cozaar'})-[r:CONTEM]->(p:PrincipioAtivo) "
    "RETURN p.nome AS principio_ativo, r.fonte_chunk_id AS fonte_chunk_id LIMIT 50"
)
```

No fim do arquivo, adicionar:

```python
@pytest.mark.parametrize(
    "cypher",
    [
        "CALL apoc.load.json('http://x') YIELD value RETURN value",
        "create (n)",
        "MATCH (n) MERGE (m)",
        "LOAD CSV FROM 'file:///x' AS l RETURN l",
        "MATCH (n) DETACH DELETE n",
        # limite documentado na spec: palavra proibida em string também é rejeitada
        "MATCH (n) WHERE n.nome = 'set' RETURN n",
    ],
)
def test_palavra_proibida_rejeitada_sem_tocar_no_neo4j(cypher):
    with pytest.raises(CypherInvalido, match="palavra proibida"):
        validar_cypher(None, cypher)  # driver None: a regex roda antes do EXPLAIN


def test_cypher_vazio_e_sem_consulta():
    with pytest.raises(CypherInvalido, match=SEM_CONSULTA):
        validar_cypher(None, "   ")


def test_sem_embedding_remove_vetores_aninhados():
    linha = {"m": {"nome": "a", "embedding_nome": [1.0]}, "l": [{"embedding": [2.0], "id": "x"}]}
    assert _sem_embedding(linha) == {"m": {"nome": "a"}, "l": [{"id": "x"}]}


def test_validar_aceita_leitura(db):
    validar_cypher(db, COZAAR)


def test_validar_rejeita_sintaxe_com_mensagem_do_neo4j(db):
    with pytest.raises(CypherInvalido, match="Invalid input"):
        validar_cypher(db, RUIM)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_text2cypher.py -v`
Expected: erro de coleta `ImportError: cannot import name 'SEM_CONSULTA'`.

- [ ] **Step 3: Implementar**

Em `src/graphrag_bulas/text2cypher.py`, trocar o bloco de imports por (ordem exigida pelo ruff, ver Global Constraints):

```python
import re

from pydantic import BaseModel, Field

from neo4j import READ_ACCESS
```

Logo abaixo dos imports, antes de `REGRAS`:

```python
TIMEOUT_S = 5
MAX_LINHAS = 50
SEM_CONSULTA = "sem_consulta"
# Também rejeita essas palavras dentro de string literal: rejeição a mais, nunca escrita liberada.
PROIBIDAS = re.compile(
    r"\b(CALL|LOAD|CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|FOREACH)\b", re.IGNORECASE
)
```

Depois de `class Consulta`:

```python
class CypherInvalido(Exception):
    pass
```

No fim do arquivo:

```python
def validar_cypher(driver, cypher):
    """Levanta CypherInvalido se a consulta for vazia, proibida, inválida ou não for só leitura."""
    if not cypher.strip():
        raise CypherInvalido(SEM_CONSULTA)
    if m := PROIBIDAS.search(cypher):
        raise CypherInvalido(f"palavra proibida: {m.group(0)}")
    try:
        with driver.session(default_access_mode=READ_ACCESS) as s:
            tipo = s.run("EXPLAIN " + cypher).consume().query_type
    except Exception as e:
        raise CypherInvalido(str(e)) from e
    if tipo != "r":
        raise CypherInvalido(f"consulta não é só leitura (tipo {tipo})")


def _sem_embedding(v):
    if isinstance(v, dict):
        return {k: _sem_embedding(x) for k, x in v.items() if not k.startswith("embedding")}
    if isinstance(v, list):
        return [_sem_embedding(x) for x in v]
    return v
```

`TIMEOUT_S` e `MAX_LINHAS` só são usados na Task 3; o ruff não reclama de constante sem uso.

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_text2cypher.py -v`
Expected: 13 passed.

- [ ] **Step 5: Lint e commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/graphrag_bulas/text2cypher.py tests/test_text2cypher.py
git commit -m "feat: adiciona validar_cypher com bloqueio de escrita e EXPLAIN (E5.3)"
```

---

### Task 3: `consultar` (gerar → validar → executar)

**Files:**
- Modify: `src/graphrag_bulas/text2cypher.py`
- Test: `tests/test_text2cypher.py`

**Interfaces:**
- Consumes: `gerar_cypher`, `validar_cypher`, `CypherInvalido`, `SEM_CONSULTA`, `_sem_embedding`, `TIMEOUT_S`, `MAX_LINHAS` (Tasks 1–2).
- Produces: `consultar(driver, llm, pergunta, seeds, tentativas=2) -> {"query": str | None, "linhas": list[dict], "erro": str | None}`. Nunca levanta exceção.

- [ ] **Step 1: Escrever os testes que falham**

No import do topo de `tests/test_text2cypher.py`, acrescentar `consultar` (ordem alfabética: depois de `_sem_embedding`, antes de `gerar_cypher`). No fim do arquivo:

```python
def contagem(db):
    q = "MATCH (n) WITH count(n) AS n MATCH ()-[r]->() RETURN n, count(r) AS r"
    return dict(db.execute_query(q).records[0])


def test_consultar_devolve_linhas(db):
    r = consultar(db, LLMFalso(COZAAR), "x", SEEDS)
    assert r == {
        "query": COZAAR,
        "linhas": [{"principio_ativo": "Losartana", "fonte_chunk_id": None}],
        "erro": None,
    }


def test_consultar_tenta_de_novo_com_o_erro(db):
    llm = LLMFalso(RUIM, COZAAR)
    r = consultar(db, llm, "x", SEEDS)
    assert r["erro"] is None and r["linhas"]
    assert RUIM in llm.prompts[1] and "Invalid input" in llm.prompts[1]


def test_consultar_desiste_apos_duas_falhas(db):
    r = consultar(db, LLMFalso(RUIM, RUIM), "x", SEEDS)
    assert r["query"] == RUIM and r["linhas"] == []
    assert "Invalid input" in r["erro"]


def test_consultar_vazio_nao_tenta_de_novo(db):
    llm = LLMFalso("")
    assert consultar(db, llm, "x", SEEDS) == {"query": None, "linhas": [], "erro": SEM_CONSULTA}
    assert len(llm.prompts) == 1


def test_consultar_bloqueia_escrita(db):
    antes = contagem(db)
    r = consultar(db, LLMFalso("CREATE (:X)", "CREATE (:X)"), "x", SEEDS)
    assert "palavra proibida" in r["erro"]
    assert contagem(db) == antes


def test_consultar_sobrevive_a_falha_do_llm(db):
    r = consultar(db, LLMFalso(RuntimeError("cota")), "x", SEEDS)
    assert r == {"query": None, "linhas": [], "erro": "llm: cota"}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_text2cypher.py -v`
Expected: erro de coleta `ImportError: cannot import name 'consultar'`.

- [ ] **Step 3: Implementar**

Em `src/graphrag_bulas/text2cypher.py`, trocar o bloco de imports por:

```python
import logging
import re

from pydantic import BaseModel, Field

from neo4j import READ_ACCESS, unit_of_work

log = logging.getLogger(__name__)
```

No fim do arquivo:

```python
@unit_of_work(timeout=TIMEOUT_S)
def _ler_linhas(tx, cypher):
    return [_sem_embedding(r.data()) for r in tx.run(cypher).fetch(MAX_LINHAS)]


def _falha(query, erro):
    log.warning("text2cypher falhou: %s | %s", erro, query)
    return {"query": query, "linhas": [], "erro": erro}


def consultar(driver, llm, pergunta, seeds, tentativas=2):
    """Gera, valida e executa o Cypher. Nunca levanta exceção; falha vai em "erro"."""
    cypher = erro = None
    for _ in range(tentativas):
        try:
            cypher = gerar_cypher(llm, pergunta, seeds, cypher, erro)
        except Exception as e:  # rede, cota ou saída inválida do LLM
            return _falha(None, f"llm: {e}")
        try:
            validar_cypher(driver, cypher)
            with driver.session(default_access_mode=READ_ACCESS) as s:
                linhas = s.execute_read(_ler_linhas, cypher)
        except CypherInvalido as e:
            if str(e) == SEM_CONSULTA:
                return _falha(None, SEM_CONSULTA)
            erro = str(e)
            continue
        except Exception as e:  # timeout ou erro na execução: sem nova tentativa
            return _falha(cypher, str(e))
        return {"query": cypher, "linhas": linhas, "erro": None}
    return _falha(cypher, erro)
```

Notas:
- `execute_read` abre transação de leitura: o servidor recusa escrita (`Writing in read access mode not allowed`) mesmo se a regex falhar.
- `unit_of_work(timeout=...)` é o jeito do driver 6 de pôr timeout numa função de transação; `tx.run` não aceita `Query`.
- `fetch(MAX_LINHAS)` corta em 50 linhas mesmo sem `LIMIT` na consulta.

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_text2cypher.py -v`
Expected: 19 passed (13 anteriores + 6 novos).

- [ ] **Step 5: Lint e commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/graphrag_bulas/text2cypher.py tests/test_text2cypher.py
git commit -m "feat: adiciona consultar com nova tentativa e execução só leitura (E5.3)"
```

---

### Task 4: Integração em `recuperar`, teste com Gemini real e README

**Files:**
- Modify: `src/graphrag_bulas/retrieval.py` (função `recuperar`, fim do arquivo; import no topo)
- Modify: `tests/test_retrieval.py` (fim do arquivo)
- Modify: `tests/test_text2cypher.py` (fim do arquivo)
- Modify: `README.md:35-37`

**Interfaces:**
- Consumes: `consultar` (Task 3); `LLMFalso`, `COZAAR`, `MAREVAN_ADVIL` de `tests/test_text2cypher.py`; `buscar_seeds`, `expandir` (E5.1/E5.2).
- Produces: `recuperar(driver, pergunta, llm=None) -> dict` com as chaves de antes (`seeds`, `subgrafo`, `trechos`) mais `cypher`: `None` sem LLM, ou o retorno de `consultar`.

- [ ] **Step 1: Escrever os testes que falham**

No fim de `tests/test_retrieval.py`:

```python
def test_recuperar_sem_llm_nao_gera_cypher(db):
    assert recuperar(db, MAREVAN_ADVIL)["cypher"] is None


def test_recuperar_com_llm_traz_linhas_do_cypher(db):
    from test_text2cypher import COZAAR, LLMFalso

    r = recuperar(db, MAREVAN_ADVIL, llm=LLMFalso(COZAAR))
    assert r["cypher"]["linhas"] and r["cypher"]["erro"] is None
    assert r["subgrafo"]["nos"]  # a expansão continua rodando
```

(`tests/` não tem `__init__.py`; o pytest põe a pasta no `sys.path`, então `from test_text2cypher import ...` funciona.)

No fim de `tests/test_text2cypher.py`:

```python
@pytest.mark.skipif(
    os.getenv("GRAPHRAG_TESTAR_LLM") != "1",
    reason="Gemini real: defina GRAPHRAG_TESTAR_LLM=1 (gasta cota, não determinístico)",
)
def test_gemini_real_gera_cypher_com_fonte(db):
    from graphrag_bulas.config import get_llm
    from graphrag_bulas.retrieval import buscar_seeds

    seeds = buscar_seeds(db, MAREVAN_ADVIL)["entidades"]
    r = consultar(db, get_llm(temperature=0), MAREVAN_ADVIL, seeds)
    assert r["erro"] is None, r
    assert any(linha.get("fonte_chunk_id") for linha in r["linhas"]), r
```

E no topo de `tests/test_text2cypher.py`, antes de `import pytest`, adicionar `import os`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_retrieval.py -v -k recuperar`
Expected: `test_recuperar_sem_llm_nao_gera_cypher` falha com `KeyError: 'cypher'`; o outro falha com `TypeError: recuperar() got an unexpected keyword argument 'llm'`.

- [ ] **Step 3: Implementar**

Em `src/graphrag_bulas/retrieval.py`, depois de `from graphrag_bulas.embeddings import embed`, adicionar:

```python
from graphrag_bulas.text2cypher import consultar
```

Trocar a função `recuperar` inteira por:

```python
def recuperar(driver, pergunta, llm=None):
    """Pergunta -> seeds -> subgrafo + trechos, e o Cypher do LLM se houver llm (E5.3)."""
    seeds = buscar_seeds(driver, pergunta)
    r = expandir(driver, seeds)
    r["cypher"] = consultar(driver, llm, pergunta, seeds["entidades"]) if llm else None
    return r
```

Em `README.md`, trocar as linhas 35–37 por:

```markdown
Retrieval do GraphRAG (E5.1 + E5.2 + E5.3), pergunta → seeds → subgrafo + trechos + Cypher
gerado pelo Gemini (sem `llm=`, roda só a expansão):

    uv run python -c "from graphrag_bulas.config import get_driver, get_llm; from graphrag_bulas.retrieval import recuperar; import json; print(json.dumps(recuperar(get_driver(), 'Posso tomar Marevan com Advil?', llm=get_llm(temperature=0)), ensure_ascii=False, indent=2))"
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest -v`
Expected: suíte toda passa; `test_gemini_real_gera_cypher_com_fonte` aparece como skipped.

Depois, uma vez, com o Gemini real:

Run: `GRAPHRAG_TESTAR_LLM=1 uv run pytest tests/test_text2cypher.py -v -k gemini`
Expected: 1 passed. Se falhar, leia a `query` no `r` da mensagem: o problema é o prompt, não o código. Pode levar minutos na primeira vez (o bge-m3 carrega; defina `HF_TOKEN` para baixar mais rápido).

- [ ] **Step 5: Lint e commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add src/graphrag_bulas/retrieval.py tests/test_retrieval.py tests/test_text2cypher.py README.md
git commit -m "feat: integra o Text-to-Cypher ao recuperar com llm opcional (E5.3)"
```
