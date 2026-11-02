# E7 — Avaliação GraphRAG vs baselines — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rodar 40 perguntas gold em `graphrag`, `rag` e `llm_puro` e gerar as tabelas do artigo.

**Architecture:** Um módulo `src/graphrag_bulas/avaliacao.py` com quatro partes: métricas puras, `validar`
do gold, `rodar` retomável (jsonl) e `relatorio` (markdown). O gold é o arquivo `data/gold/perguntas.json`.

**Tech Stack:** Python 3.13, pytest, LangChain structured output, Neo4j driver (via `config`).

**Spec:** `docs/superpowers/specs/2026-11-02-e7-avaliacao-design.md`

## Global Constraints

- Corpus fixo: 25 bulas extraídas. Fontes válidas = chunk_ids de `data/processed/chunks.jsonl` dessas bulas.
- 40 perguntas: 15 `1hop`, 15 `multihop`, 10 `sem_resposta`.
- Sem LLM juiz. Casamento de fatos com `chunks.slug` dos dois lados, por substring.
- Commits semânticos em pt-BR.
- Testes sem Neo4j e sem LLM real.

---

### Task 1: Métricas e validação do gold

**Files:**
- Create: `src/graphrag_bulas/avaliacao.py`
- Test: `tests/test_avaliacao.py`

**Interfaces:**
- Produces: `cobertura(resposta: str, fatos: list[list[str]]) -> float`,
  `metricas(pergunta: dict, linha: dict) -> dict`, `validar_gold(gold: dict, chunk_ids: set[str]) -> list[str]`,
  `CONTAGEM = {"1hop": 15, "multihop": 15, "sem_resposta": 10}`.

- [ ] **Step 1: Write the failing tests**

```python
from graphrag_bulas.avaliacao import cobertura, metricas, validar_gold

P1 = {"id": "q1", "tipo": "1hop", "fatos": [["tontura"], ["hemorragia", "sangramento"]],
      "fontes": ["c1"]}
PS = {"id": "q2", "tipo": "sem_resposta", "fatos": [], "fontes": []}


def linha(**kw):
    return {"resposta": "", "recusou": False, "citados": [], "erro": None, **kw}


def test_cobertura_ignora_acento_maiuscula_e_aceita_variante():
    assert cobertura("Pode causar TONTURA e Sangramento.", P1["fatos"]) == 1.0
    assert cobertura("Pode causar tontura.", P1["fatos"]) == 0.5


def test_metricas_pergunta_com_resposta():
    m = metricas(P1, linha(resposta="tontura", citados=["c1", "c9"]))
    assert m == {"cobertura": 0.5, "acerto": 0, "recusa_falsa": 0, "fidelidade": 0.5}


def test_metricas_recusa_zera_cobertura_e_fidelidade_indefinida():
    m = metricas(P1, linha(resposta="tontura sangramento", recusou=True))
    assert m == {"cobertura": 0.0, "acerto": 0, "recusa_falsa": 1, "fidelidade": None}


def test_metricas_sem_resposta():
    assert metricas(PS, linha(recusou=True)) == {"recusa_correta": 1, "alucinacao": 0}
    assert metricas(PS, linha()) == {"recusa_correta": 0, "alucinacao": 1}


def test_metricas_linha_com_erro_e_none():
    assert metricas(P1, linha(erro="boom")) is None


def test_validar_gold():
    perguntas = ([{**P1, "id": f"a{i}"} for i in range(15)]
                 + [{**P1, "id": f"b{i}", "tipo": "multihop"} for i in range(15)]
                 + [{**PS, "id": f"c{i}"} for i in range(10)])
    assert validar_gold({"perguntas": perguntas}, {"c1"}) == []
    erros = validar_gold({"perguntas": perguntas}, set())
    assert any("c1" in e for e in erros)
    erros = validar_gold({"perguntas": perguntas[:-1] + [perguntas[0]]}, {"c1"})
    assert any("repetido" in e for e in erros) and any("sem_resposta" in e for e in erros)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_avaliacao.py -q` — Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
"""Avaliação GraphRAG vs baselines (E7): gold de perguntas, rodada e relatório.

Spec: docs/superpowers/specs/2026-11-02-e7-avaliacao-design.md
"""

from collections import Counter

from graphrag_bulas.chunks import slug

CONTAGEM = {"1hop": 15, "multihop": 15, "sem_resposta": 10}


def cobertura(resposta, fatos):
    """Fração dos fatos com alguma variante dentro da resposta (slug dos dois lados)."""
    r = slug(resposta)
    return sum(any(slug(v) in r for v in fato) for fato in fatos) / len(fatos)


def metricas(pergunta, linha):
    """Métricas de uma resposta; None se a linha tem erro."""
    if linha["erro"]:
        return None
    if pergunta["tipo"] == "sem_resposta":
        return {"recusa_correta": int(linha["recusou"]), "alucinacao": int(not linha["recusou"])}
    cob = 0.0 if linha["recusou"] else cobertura(linha["resposta"], pergunta["fatos"])
    citados = linha["citados"]
    fid = (sum(c in pergunta["fontes"] for c in citados) / len(citados)) if citados else None
    return {"cobertura": cob, "acerto": int(cob == 1.0), "recusa_falsa": int(linha["recusou"]),
            "fidelidade": fid}


def validar_gold(gold, chunk_ids):
    """Erros do gold de perguntas: ids, contagem por tipo, fatos/fontes e fontes inexistentes."""
    ps = gold["perguntas"]
    erros = [f"id repetido: {i}" for i, n in Counter(p["id"] for p in ps).items() if n > 1]
    tipos = Counter(p["tipo"] for p in ps)
    erros += [f"{t}: {tipos[t]} perguntas, esperado {n}" for t, n in CONTAGEM.items()
              if tipos[t] != n]
    for p in ps:
        tem = bool(p["fatos"]) and bool(p["fontes"])
        if (p["tipo"] == "sem_resposta") == tem:
            erros.append(f"{p['id']}: fatos/fontes não batem com o tipo {p['tipo']}")
        erros += [f"{p['id']}: fonte {c} não existe" for c in p["fontes"] if c not in chunk_ids]
    return erros
```

- [ ] **Step 4: Run tests** — `uv run pytest tests/test_avaliacao.py -q` — Expected: PASS.

- [ ] **Step 5: Commit** — `feat: métricas e validação do gold de perguntas (E7.1, E7.4)`

---

### Task 2: Modo `llm_puro`, `rodar`, `relatorio` e CLI

**Files:**
- Modify: `src/graphrag_bulas/avaliacao.py`
- Test: `tests/test_avaliacao.py`

**Interfaces:**
- Consumes: `metricas`, `validar_gold`, `CONTAGEM` (Task 1); `api.responder(pergunta, modo, driver, llm)`;
  `geracao.Resposta`.
- Produces: `responder_llm_puro(llm, pergunta) -> dict`,
  `rodar(perguntas, modos, responder, saida: Path) -> int` (nº de linhas novas),
  `relatorio(perguntas, linhas) -> str`, `main(argv=None)` com subcomandos `validar`, `rodar [--modo M]`,
  `relatorio`.

- [ ] **Step 1: Write the failing tests** (acrescentar ao arquivo)

```python
import json

from graphrag_bulas.avaliacao import relatorio, responder_llm_puro, rodar
from graphrag_bulas.geracao import Resposta


class LLMFalso:
    def __init__(self, r):
        self.r = r

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        return self.r


def test_llm_puro_recusa_com_suporte_nenhum():
    r = Resposta(resposta="Não sei.", chunks=[], nos=[], suporte="nenhum")
    assert responder_llm_puro(LLMFalso(r), "x")["recusou"] is True
    r = Resposta(resposta="Sim.", chunks=[], nos=[], suporte="total")
    out = responder_llm_puro(LLMFalso(r), "x")
    assert out["recusou"] is False and out["trechos"] == []


def test_rodar_grava_retoma_e_registra_erro(tmp_path):
    saida = tmp_path / "r.jsonl"
    chamadas = []

    def resp(pergunta, modo):
        chamadas.append((pergunta, modo))
        if pergunta == "ruim":
            raise RuntimeError("boom")
        return {"resposta": "tontura", "recusou": False, "confianca": 0.9,
                "trechos": [{"chunk_id": "c1", "citado": True}, {"chunk_id": "c2", "citado": False}]}

    ps = [{"id": "q1", "pergunta": "boa"}, {"id": "q2", "pergunta": "ruim"}]
    assert rodar(ps, ["rag"], resp, saida) == 2
    linhas = [json.loads(x) for x in saida.read_text().splitlines()]
    assert linhas[0]["citados"] == ["c1"] and linhas[1]["erro"] == "RuntimeError: boom"
    chamadas.clear()
    rodar(ps, ["rag"], resp, saida)
    assert chamadas == [("ruim", "rag")]


def test_relatorio_tem_tabelas_e_aviso():
    ps = [P1, PS]
    linhas = [{"id": "q1", "modo": "rag", "segundos": 2.0, **linha(resposta="tontura sangramento",
                                                                   citados=["c1"])},
              {"id": "q2", "modo": "rag", "segundos": 1.0, **linha(recusou=True)}]
    md = relatorio(ps, linhas)
    assert "| rag | 1.000 | 1.000 | 1.000 | 0.000 | 1.000 | 0.000 | 1.5 | 0 |" in md
    assert "sem revisão humana" in md
```

- [ ] **Step 2: Run to verify it fails** — Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement** (acrescentar ao módulo; imports no topo)

```python
import argparse
import json
import sys
import time
from pathlib import Path

from graphrag_bulas.chunks import PROCESSADOS
from graphrag_bulas.geracao import RECUSA, Resposta

RAIZ = Path(__file__).resolve().parents[2]
GOLD = RAIZ / "data" / "gold" / "perguntas.json"
RESPOSTAS = RAIZ / "logs" / "e7" / "respostas.jsonl"
RELATORIO = RAIZ / "logs" / "avaliacao_e7.md"
MODOS = ("graphrag", "rag", "llm_puro")

PROMPT_PURO = """Você responde perguntas sobre medicamentos, em português, com o seu conhecimento.
Se não souber responder com segurança, use suporte = nenhum. Deixe chunks e nos vazios.
Em pergunta sobre interação, contraindicação ou dose, oriente procurar médico ou farmacêutico.

Pergunta: {pergunta}"""


def responder_llm_puro(llm, pergunta):
    """Baseline sem contexto (E7.3): mesmo LLM e mesmo schema de resposta do E5.6."""
    r = llm.with_structured_output(Resposta).invoke(PROMPT_PURO.format(pergunta=pergunta))
    recusou = r.suporte == "nenhum"
    return {"resposta": RECUSA if recusou else r.resposta, "recusou": recusou,
            "confianca": 0.0 if recusou else None, "trechos": []}


def rodar(perguntas, modos, responder, saida):
    """Uma linha por (pergunta, modo) em saida; pula o que já deu certo. Devolve linhas novas."""
    saida.parent.mkdir(parents=True, exist_ok=True)
    feitos = set()
    if saida.exists():
        feitos = {(x["id"], x["modo"]) for x in map(json.loads, saida.read_text().splitlines())
                  if not x["erro"]}
    novas = 0
    with saida.open("a", encoding="utf-8") as f:
        for modo in modos:
            for p in perguntas:
                if (p["id"], modo) in feitos:
                    continue
                t0, linha = time.monotonic(), {"id": p["id"], "modo": modo, "erro": None}
                try:
                    r = responder(p["pergunta"], modo)
                    linha |= {"resposta": r["resposta"], "recusou": r["recusou"],
                              "confianca": r["confianca"],
                              "citados": [t["chunk_id"] for t in r["trechos"] if t.get("citado")]}
                except Exception as e:  # uma pergunta ruim não para a rodada
                    linha |= {"resposta": "", "recusou": False, "confianca": None, "citados": [],
                              "erro": f"{type(e).__name__}: {e}"}
                linha["segundos"] = round(time.monotonic() - t0, 1)
                f.write(json.dumps(linha, ensure_ascii=False) + "\n")
                f.flush()
                novas += 1
                print(f"{modo} {p['id']} {linha['segundos']}s {linha['erro'] or ''}", flush=True)
    return novas


def _media(xs):
    xs = [x for x in xs if x is not None]
    return f"{sum(xs) / len(xs):.3f}" if xs else "—"


def relatorio(perguntas, linhas):
    """Markdown com a tabela geral por modo e cobertura/acerto por modo x tipo."""
    por_id = {p["id"]: p for p in perguntas}
    ultima = {(x["id"], x["modo"]): x for x in linhas if x["id"] in por_id}  # última tentativa vale
    modos = [m for m in MODOS if any(k[1] == m for k in ultima)]
    cab = ["cobertura", "acerto", "fidelidade", "recusa_falsa", "recusa_correta", "alucinacao"]
    md = ["# Avaliação GraphRAG vs baselines (E7)", "",
          f"**Perguntas sem revisão humana** (escritas pelo Claude a partir das bulas). "
          f"{len(perguntas)} perguntas.", "", "## Geral",
          "| modo | " + " | ".join(cab) + " | tempo médio (s) | erros |",
          "|---" * (len(cab) + 3) + "|"]
    tipos_md = ["", "## Por tipo", "| modo | tipo | cobertura | acerto |", "|---|---|---|---|"]
    for m in modos:
        ls = [x for k, x in ultima.items() if k[1] == m]
        ms = [(por_id[x["id"]]["tipo"], metricas(por_id[x["id"]], x)) for x in ls]
        ok = [(t, v) for t, v in ms if v is not None]
        cel = [_media(v.get(c) for _, v in ok if c in v) for c in cab]
        tempo = sum(x["segundos"] for x in ls) / len(ls)
        md.append(f"| {m} | " + " | ".join(cel) + f" | {tempo:.1f} | {len(ms) - len(ok)} |")
        for t in ("1hop", "multihop"):
            vs = [v for tt, v in ok if tt == t]
            tipos_md.append(f"| {m} | {t} | {_media(v['cobertura'] for v in vs)} | "
                            f"{_media(v['acerto'] for v in vs)} |")
    return "\n".join(md + tipos_md) + "\n"


def _ler_jsonl(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("comando", choices=["validar", "rodar", "relatorio"])
    p.add_argument("--modo", action="append", choices=MODOS, help="repetível; padrão: os três")
    a = p.parse_args(argv)
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    if a.comando == "validar":
        ids = {c["id"] for c in _ler_jsonl(PROCESSADOS / "chunks.jsonl")}
        erros = validar_gold(gold, ids)
        print("\n".join(erros) or f"ok: {len(gold['perguntas'])} perguntas")
        return 1 if erros else 0
    if a.comando == "relatorio":
        RELATORIO.write_text(relatorio(gold["perguntas"], _ler_jsonl(RESPOSTAS)), encoding="utf-8")
        print(RELATORIO.read_text(encoding="utf-8"))
        return 0
    from graphrag_bulas.api import responder
    from graphrag_bulas.config import get_driver, get_llm

    llm = get_llm(temperature=0)
    with get_driver() as d:
        def resp(pergunta, modo):
            if modo == "llm_puro":
                return responder_llm_puro(llm, pergunta)
            return responder(pergunta, modo, d, llm)

        rodar(gold["perguntas"], a.modo or list(MODOS), resp, RESPOSTAS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests** — `uv run pytest tests/test_avaliacao.py -q && uv run ruff check src tests` — Expected: PASS.

- [ ] **Step 5: Commit** — `feat: rodada retomável e relatório GraphRAG vs baselines (E7.3, E7.4, E7.5)`

---

### Task 3: Gold de 40 perguntas

**Files:**
- Create: `data/gold/perguntas.json`
- Modify: `data/gold/LEIAME.md` (seção "Perguntas (E7.1)")

- [ ] **Step 1:** Ler os chunks das 25 bulas (`chunks.jsonl`) e escrever 15 `1hop`, 15 `multihop` e
  10 `sem_resposta` no formato da spec, com `"anotador": "claude (sem revisão humana)"`. Cada fato
  sai de uma frase literal do chunk-fonte, com variantes de grafia/sinônimo comuns. As perguntas
  `multihop` cruzam bulas ou seções (classe → medicamentos, interação + efeito, princípio ativo comum).
  As `sem_resposta` citam medicamentos fora do corpus ou dados que nenhuma bula traz.
- [ ] **Step 2:** `uv run python -m graphrag_bulas.avaliacao validar` — Expected: `ok: 40 perguntas`.
- [ ] **Step 3:** Conferir com `grep` que cada variante de fato aparece no texto de alguma fonte
  (script descartável no scratchpad).
- [ ] **Step 4:** Seção no LEIAME com formato, tipos e a ressalva de não ter revisão humana.
- [ ] **Step 5: Commit** — `docs: gold de 40 perguntas para a avaliação (E7.1)`

---

### Task 4: Rodada e relatório

- [ ] **Step 1:** Neo4j no ar (`docker compose up -d`). Em background:
  `caffeinate -i uv run --extra embeddings python -m graphrag_bulas.avaliacao rodar > logs/e7/rodada.log 2>&1`.
- [ ] **Step 2:** Ao terminar, rodar de novo para refazer as linhas com erro (só elas rodam).
- [ ] **Step 3:** `uv run python -m graphrag_bulas.avaliacao relatorio` e ler `logs/avaliacao_e7.md`.
- [ ] **Step 4:** Rodar a suíte inteira (`uv run --extra embeddings pytest -q`).
- [ ] **Step 5:** Relatar os números ao usuário. `logs/` é ignorado pelo git: copiar o relatório final para
  `docs/resultados/avaliacao_e7.md` e commitar (`docs: resultados da avaliação E7 (E7.5)`).
