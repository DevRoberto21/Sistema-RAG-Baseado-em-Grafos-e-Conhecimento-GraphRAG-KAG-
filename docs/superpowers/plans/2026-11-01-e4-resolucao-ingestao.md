# E4 — Resolução de entidades e ingestão no Neo4j — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Levar as 3185 relações de `data/processed/extracoes.jsonl` (25 bulas) para o Neo4j, com as entidades duplicadas fundidas e o grafo semente preservado, mais o relatório de antes e depois para o artigo (E4.5).

**Architecture:** Duas etapas com arquivo intermediário. `resolucao.py` aplica regra, dicionário curado e similaridade de embedding, e grava `data/processed/grafo.jsonl`. `ingestao.py` aplica schema e seed, carrega documentos, nós, relações, `MENCIONA` e embeddings com `UNWIND` + `MERGE` em lotes. A resolução é pura (testável sem Neo4j e sem modelo); a carga é idempotente.

**Tech Stack:** Python 3.12, driver `neo4j`, bge-m3 via `graphrag_bulas.embeddings.embed` (extra `embeddings`), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-01-e4-resolucao-ingestao-design.md`

**Status de validação:** o código final das Tasks 2–7 rodou em 2026-11-01 numa cópia do repo: suíte com 103 passed, ruff check e ruff format limpos. A resolução rodou sobre o `extracoes.jsonl` real com embedding falso (1766 → 1628 nós, 3185 → 2808 relações). **Não validado:** o teste com Neo4j (`test_carga_idempotente_e_preserva_seed`) e a carga real, porque o Docker estava parado. Se falharem, confira primeiro o ambiente (Docker, `docker compose up -d`, seed carregado).

## Global Constraints

- Branch: `e4/resolucao-ingestao`, criada a partir da `main` (a spec já está commitada na `main`).
- Commits em pt-BR, semânticos (`feat:`, `test:`, `docs:`, `fix:`), **sem** linha `Co-Authored-By` nem assinatura do Claude.
- Lint: `uv run ruff check .` limpo e `uv run ruff format --check src tests` limpo (linha máx. 100).
- Testes com Neo4j usam a fixture `db` de `tests/conftest.py`: pulam sem Neo4j ou sem grafo semente.
- Rodar sempre com `uv run`. Scripts que usam bge-m3 precisam de `uv run --extra embeddings`.
- Escopo: só as 25 bulas que estão em `extracoes.jsonl`. Os 8 chunks sem extração ficam fora (o texto deles entra, sem relações).
- Não mudar `cypher/seed.cypher` nem o retrieval do E5.
- `logs/` é ignorado pelo git (`.gitignore`): relatório e pares candidatos não são commitados. `data/curadoria/` é commitado.

## Arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `src/graphrag_bulas/resolucao.py` | criar | normalização, dicionário, agrupamento por embedding, `resolver`, relatório da resolução, CLI |
| `data/curadoria/sinonimos.json` | criar | dicionário curado: `{label: {id_canonico: [variantes]}}` |
| `src/graphrag_bulas/ingestao.py` | criar | linhas para o Neo4j, carga com `MERGE`, contagens, relatório da carga, CLI |
| `tests/test_resolucao.py` | criar | testes da resolução, sem Neo4j e sem modelo |
| `tests/test_ingestao.py` | criar | testes da montagem das linhas e da carga (fixture `db`) |
| `tests/test_seed.py`, `tests/test_retrieval.py`, `tests/test_gds.py`, `tests/test_text2cypher.py`, `tests/test_api.py`, `tests/test_contexto.py`, `tests/test_rag_vetorial.py`, `tests/test_embeddings.py` | ajustar (Task 8) | asserções que supõem só o grafo semente |
| `README.md` | modificar | seção de uso do E4 |

---

### Task 1: Branch e commit da correção pendente do `validar`

A correção do `validar` (mapa `COMPOSICAO`, sinônimos de população, redirecionamento de `INTERAGE_COM`/`PERTENCE_A`/`CONTRAINDICADO_EM` para o princípio ativo) já está no working tree da `main`, sem commit. O `resolucao.py` importa `COMPOSICAO` dela.

**Files:**
- Modify (já modificados): `src/graphrag_bulas/extracao.py`, `tests/test_extracao.py`

**Interfaces:**
- Produces: `graphrag_bulas.extracao.COMPOSICAO: dict[str, list[str]]` (id do medicamento → ids de princípio ativo).

- [ ] **Step 1: Criar a branch levando as mudanças**

```bash
git switch -c e4/resolucao-ingestao
git status --short
```
Expected: `M src/graphrag_bulas/extracao.py` e `M tests/test_extracao.py`.

- [ ] **Step 2: Rodar os testes**

Run: `uv run pytest -q tests/test_extracao.py && uv run ruff check src tests`
Expected: todos passam; `All checks passed!`

- [ ] **Step 3: Commit**

```bash
git add src/graphrag_bulas/extracao.py tests/test_extracao.py
git commit -m "fix: corrige pontas e populações rejeitadas pela validação da extração"
```

---

### Task 2: Normalização por regra (E4.1)

**Files:**
- Create: `src/graphrag_bulas/resolucao.py`
- Test: `tests/test_resolucao.py`

**Interfaces:**
- Consumes: `graphrag_bulas.chunks.slug(nome: str) -> str`, `graphrag_bulas.chunks.PROCESSADOS: Path`.
- Produces: `normalizar(id_: str, label: str) -> str`, `bloqueado(a: str, b: str) -> bool`, constantes `RAIZ`, `DICIONARIO`, `ROTULADOS`, `ENTRADA`, `SAIDA`, `PARES`, `RELATORIO`, `LIMIAR_PADRAO = 0.92`, `FAIXA_PARES = (0.80, 0.95)`, `SEM_EMBEDDING`.

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_resolucao.py`:

```python
"""Resolução de entidades (E4.1, E4.2). Sem Neo4j e sem modelo: embedding falso."""

import pytest

from graphrag_bulas import resolucao as rz


@pytest.mark.parametrize(
    "id_,label,esperado",
    [
        ("losartana_potassica", "PrincipioAtivo", "losartana"),
        ("carbonato_de_litio", "PrincipioAtivo", "litio"),
        ("olmesartana_medoxomila", "PrincipioAtivo", "olmesartana"),
        ("aines", "ClasseTerapeutica", "aine"),
        ("betabloqueadores", "ClasseTerapeutica", "betabloqueador"),
        ("bloqueadores_dos_canais_de_calcio", "ClasseTerapeutica", "bloqueador_do_canal_de_calcio"),
        ("inhibidores_da_eca", "ClasseTerapeutica", "inibidor_da_eca"),
        ("diabetes", "Condicao", "diabetes"),
        ("Insuficiência Renal", "Condicao", "insuficiencia_renal"),
    ],
)
def test_normalizar(id_, label, esperado):
    assert rz.normalizar(id_, label) == esperado


@pytest.mark.parametrize(
    "a,b,esperado",
    [
        ("hipertensao", "hipotensao", True),
        ("hipocalemia", "hipercalemia", True),
        ("bradicardia", "taquicardia", True),
        ("tontura", "vertigem", False),
    ],
)
def test_bloqueado(a, b, esperado):
    assert rz.bloqueado(a, b) is esperado
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest -q tests/test_resolucao.py`
Expected: FAIL com `ModuleNotFoundError: No module named 'graphrag_bulas.resolucao'`.

- [ ] **Step 3: Implementar**

`src/graphrag_bulas/resolucao.py`:

```python
"""Resolução de entidades (E4.1, E4.2): extracoes.jsonl -> grafo.jsonl.

Uso:
  uv run --extra embeddings python -m graphrag_bulas.resolucao

Três passos por label: regra (normalizar), dicionário curado (data/curadoria/sinonimos.json)
e similaridade de embedding com limiar. Grava data/processed/grafo.jsonl,
logs/pares_candidatos.csv e a primeira parte de logs/relatorio_e4.md.
Spec: docs/superpowers/specs/2026-11-01-e4-resolucao-ingestao-design.md
"""

import re

from graphrag_bulas.chunks import PROCESSADOS, slug

RAIZ = PROCESSADOS.parents[1]
DICIONARIO = RAIZ / "data" / "curadoria" / "sinonimos.json"
ROTULADOS = RAIZ / "data" / "curadoria" / "pares_rotulados.csv"
ENTRADA = PROCESSADOS / "extracoes.jsonl"
SAIDA = PROCESSADOS / "grafo.jsonl"
PARES = RAIZ / "logs" / "pares_candidatos.csv"
RELATORIO = RAIZ / "logs" / "relatorio_e4.md"

LIMIAR_PADRAO = 0.92
FAIXA_PARES = (0.80, 0.95)
SEM_EMBEDDING = {"Medicamento", "Populacao", "Fabricante"}  # vocabulário fechado

GRAFIA = {
    "inhibidor": "inibidor",
    "inhibidores": "inibidores",
    "sistematico": "sistemico",
    "sistematicos": "sistemicos",
}
SAL_PREFIXO = re.compile(
    r"^(cloridrato|dicloridrato|maleato|carbonato|besilato|sulfato|fosfato|succinato|"
    r"tartarato|acetato|citrato|mesilato)_de_"
)
SAL_SUFIXO = re.compile(
    r"_(potassica|potassico|sodica|sodico|calcica|calcico|magnesica|medoxomila|"
    r"monoidratad[ao]|di_?hidratad[ao]|tri_?hidratad[ao])$"
)
OPOSTOS = [("hiper", "hipo"), ("bradi", "taqui"), ("aumento", "diminuicao"), ("aumento", "reducao")]


def _singular(p: str) -> str:
    if p.endswith(("res", "zes")):
        return p[:-2]
    if p.endswith("ais"):
        return p[:-3] + "al"
    if p.endswith("s") and not p.endswith("ss") and len(p) > 2:
        return p[:-1]
    return p


def normalizar(id_: str, label: str) -> str:
    """Regras do E4.1: grafia; sal em PrincipioAtivo; singular em ClasseTerapeutica."""
    partes = [GRAFIA.get(p, p) for p in slug(id_).split("_")]
    if label == "ClasseTerapeutica":
        partes = [_singular(p) for p in partes]
    id_ = "_".join(partes)
    if label == "PrincipioAtivo":
        id_ = SAL_SUFIXO.sub("", SAL_PREFIXO.sub("", id_))
    return id_


def bloqueado(a: str, b: str) -> bool:
    """Nomes com prefixo de sentido oposto (hipertensao/hipotensao) nunca se fundem."""
    return any((x in a and y in b) or (y in a and x in b) for x, y in OPOSTOS)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest -q tests/test_resolucao.py && uv run ruff check src tests`
Expected: 13 passed; `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add src/graphrag_bulas/resolucao.py tests/test_resolucao.py
git commit -m "feat: normalização de ids de entidade para a resolução (E4.1)"
```

---

### Task 3: Dicionário curado de sinônimos (E4.1)

**Files:**
- Create: `data/curadoria/sinonimos.json`
- Modify: `src/graphrag_bulas/resolucao.py`
- Test: `tests/test_resolucao.py`

**Interfaces:**
- Consumes: `normalizar` (Task 2), `graphrag_bulas.extracao.COMPOSICAO` (Task 1).
- Produces: `carregar_dicionario(path: Path = DICIONARIO) -> dict[str, dict[str, str]]` — `{label: {variante normalizada: id canônico}}`; o canônico também mapeia para si mesmo. Inclui `Fabricante` (usado pela ingestão, Task 6).

- [ ] **Step 1: Escrever os testes que falham** (acrescentar ao fim de `tests/test_resolucao.py`)

```python
def test_carregar_dicionario_normaliza_variantes_e_inclui_nome_comercial(tmp_path):
    arq = tmp_path / "sinonimos.json"
    arq.write_text(
        '{"ClasseTerapeutica": {"aine": ["AINEs", "anti-inflamatórios não esteroides"]}}'
    )
    dic = rz.carregar_dicionario(arq)
    assert dic["ClasseTerapeutica"] == {"aine": "aine", "anti_inflamatorio_nao_esteroide": "aine"}
    assert dic["PrincipioAtivo"]["cipro"] == "ciprofloxacino"
    assert "bactrim" not in dic["PrincipioAtivo"]  # dois princípios ativos: ambíguo


def test_dicionario_do_repo_carrega():
    dic = rz.carregar_dicionario()
    assert dic["ClasseTerapeutica"]["inibidor_da_eca"] == "ieca"
    assert dic["Fabricante"]["organon_farmaceutica_ltda"] == "organon"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest -q tests/test_resolucao.py -k dicionario`
Expected: FAIL com `AttributeError: module 'graphrag_bulas.resolucao' has no attribute 'carregar_dicionario'`.

- [ ] **Step 3: Criar `data/curadoria/sinonimos.json`**

Canônicos de `Condicao`, `EfeitoAdverso`, `Populacao`, `Fabricante` e dos 5 princípios ativos vêm do `cypher/seed.cypher`, com os mesmos sinônimos. As classes trazem as variantes vistas na extração de 2026-11-01.

```json
{
  "ClasseTerapeutica": {
    "aine": ["AINE", "AINEs", "anti-inflamatórios não esteroides", "anti-inflamatório não esteroidal", "antiinflamatório não esteroide", "antiinflamatório não esteroidal", "anti-inflamatório não hormonal", "analgésicos anti-inflamatórios"],
    "ieca": ["IECA", "inibidor da ECA", "inibidores da enzima conversora de angiotensina", "inibidor da enzima conversora da angiotensina"],
    "bra": ["BRA", "ARA II", "antagonistas de receptores da angiotensina II", "antagonista do receptor da angiotensina II", "antagonista de receptor da angiotensina II", "antagonista do receptor de angiotensina II", "antagonista de receptor de angiotensina II", "antagonista de receptor da angiotensina", "antagonista da angiotensina II", "bloqueador do receptor de angiotensina", "bloqueador do receptor de angiotensina II"],
    "anti_hipertensivo": ["agentes anti-hipertensivos", "antihipertensivo"],
    "anticoagulante": ["anticoagulantes orais", "agente anticoagulante"],
    "salicilato": ["salicilatos"],
    "betabloqueador": ["beta-bloqueador", "beta blocker"],
    "bloqueador_do_canal_de_calcio": ["bloqueador de canal de cálcio", "bloqueadores dos canais de cálcio", "calcium channel blocker"],
    "corticosteroide": ["corticoide", "corticoide sistêmico", "corticosteroide sistêmico"],
    "glicocorticoide": ["glicocorticoide sistêmico", "glicocordicoide sistêmico"],
    "digitalico": ["digital", "glicosídeo digitálico"],
    "inibidor_da_agregacao_plaquetaria": ["inibidor de agregação plaquetária", "antiplaquetário", "agente antiplaquetário"],
    "trombolitico": ["agente trombolítico", "fibrinolítico"],
    "estatina": ["statin"],
    "sulfonilureia": ["sulfonilur eia"],
    "inibidor_da_neprilisina": ["inibidor de neprilisina"],
    "inibidor_da_mtor": ["inibidor de mTOR"],
    "inibidor_seletivo_da_recaptacao_da_serotonina": ["inibidor seletivo da recaptação de serotonina", "ISRS"],
    "diuretico_poupador_de_potassio": ["diurético poupador de potásio"]
  },
  "PrincipioAtivo": {
    "losartana": ["losartana potássica"],
    "enalapril": ["maleato de enalapril"],
    "varfarina": ["varfarina sódica"],
    "ibuprofeno": [],
    "acido_acetilsalicilico": ["AAS"],
    "litio": ["lito"],
    "sulfametoxazol": ["SMZ"],
    "trimetoprima": ["TMP"]
  },
  "Condicao": {
    "hipertensao": ["pressão alta", "hipertensão essencial"],
    "insuficiencia_cardiaca": [],
    "tromboembolismo": ["tromboembolismo venoso", "embolismo sistêmico"],
    "febre": [],
    "cefaleia": ["dor de cabeça"],
    "dor_muscular": ["mialgia"],
    "dismenorreia": ["cólica menstrual"],
    "insuficiencia_hepatica": ["doença hepática grave"],
    "ulcera_peptica": ["úlcera gastrintestinal", "doença ulcerativa do trato gastrointestinal"],
    "hemorragia": ["sangramento"],
    "hemofilia": [],
    "dengue": [],
    "angioedema_hereditario": ["angioedema idiopático"]
  },
  "EfeitoAdverso": {
    "tontura": [], "vertigem": [], "cefaleia": ["dor de cabeça"], "fadiga": [],
    "astenia": ["fraqueza"], "tosse": [], "hipercalemia": ["potássio alto"],
    "hipotensao": ["pressão baixa", "hipotensão ortostática"],
    "angioedema": ["edema angioneurótico"], "alopecia": ["queda de cabelo"],
    "hemorragia": ["sangramento"], "nausea": ["enjoo"], "dispepsia": ["má digestão"],
    "diarreia": [], "zumbido": ["tinido", "tinitos"], "urticaria": [],
    "ulcera_gastrointestinal": ["úlcera gastrintestinal"],
    "hemorragia_gastrointestinal": ["sangramento gastrintestinal"]
  },
  "Populacao": {
    "gestante": ["gravidez", "grávida", "gestação"],
    "lactante": ["amamentação", "lactação"],
    "pediatrico": ["crianças", "menores de 12 anos"],
    "idoso": ["idosos"]
  },
  "Fabricante": {
    "organon": ["Organon Farmacêutica Ltda."],
    "farmoquimica": ["Farmoquímica S/A"],
    "pf_consumer": ["PF Consumer Healthcare Brazil Importadora e Distribuidora de Medicamentos Ltda."],
    "bayer": ["Bayer S.A."]
  }
}
```

- [ ] **Step 4: Implementar `carregar_dicionario`**

Em `src/graphrag_bulas/resolucao.py`, trocar o bloco de imports por:

```python
import json
import re
from pathlib import Path

from graphrag_bulas.chunks import PROCESSADOS, slug
from graphrag_bulas.extracao import COMPOSICAO
```

E acrescentar ao fim do arquivo:

```python
def carregar_dicionario(path: Path = DICIONARIO) -> dict[str, dict[str, str]]:
    """{label: {variante normalizada: id canônico}}. Inclui nome comercial -> princípio ativo."""
    bruto = json.loads(path.read_text())
    bruto.setdefault("PrincipioAtivo", {})
    for med, pas in COMPOSICAO.items():
        if len(pas) == 1:
            bruto["PrincipioAtivo"].setdefault(pas[0], []).append(med)
    dic = {}
    for label, grupos in bruto.items():
        dic[label] = {}
        for canon, variantes in grupos.items():
            for v in [canon, *variantes]:
                dic[label][normalizar(v, label)] = canon
    return dic
```

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest -q tests/test_resolucao.py && uv run ruff check src tests`
Expected: 15 passed; `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add data/curadoria/sinonimos.json src/graphrag_bulas/resolucao.py tests/test_resolucao.py
git commit -m "feat: dicionário curado de sinônimos para a resolução de entidades (E4.1)"
```

---

### Task 4: Agrupamento por embedding e escolha do limiar (E4.2)

**Files:**
- Modify: `src/graphrag_bulas/resolucao.py`
- Test: `tests/test_resolucao.py`

**Interfaces:**
- Consumes: `bloqueado` (Task 2), `LIMIAR_PADRAO`, `FAIXA_PARES`, `ROTULADOS`.
- Produces:
  - `agrupar(itens: dict[str, int], canonicos: set[str], vetores: dict[str, list[float]], limiar: float) -> tuple[dict[str, str], list[tuple[str, str, float]], list[tuple[str, str, float]]]` — `(mapa id→representante, fusões (de, para, cos), pares (id, representante, cos) na FAIXA_PARES)`.
  - `escolher_limiar(rotulados: list[tuple[float, bool]], alvo=0.95, padrao=LIMIAR_PADRAO) -> float`.
  - `ler_rotulados(path: Path = ROTULADOS) -> list[tuple[float, bool]] | None`.

- [ ] **Step 1: Escrever os testes que falham** (acrescentar ao fim de `tests/test_resolucao.py`)

```python
VETORES = {
    "tosse": [1.0, 0.0, 0.0],
    "tosse_seca": [0.9, 0.43589, 0.0],
    "hipotensao": [0.0, 1.0, 0.0],
    "hipertensao": [0.0, 1.0, 0.0],
    "tontura": [0.0, 0.0, 1.0],
}
ITENS = {"tosse": 5, "tosse_seca": 1, "hipotensao": 3, "hipertensao": 2, "tontura": 4}


def test_agrupar_funde_acima_do_limiar_e_respeita_bloqueio():
    mapa, fusoes, pares = rz.agrupar(ITENS, {"tosse"}, VETORES, limiar=0.85)
    assert mapa["tosse_seca"] == "tosse"
    assert mapa["hipertensao"] == "hipertensao"  # vetor igual ao de hipotensao, mas bloqueado
    assert [(de, para) for de, para, _ in fusoes] == [("tosse_seca", "tosse")]
    assert [(i, r) for i, r, _ in pares] == [("tosse_seca", "tosse")]


def test_agrupar_abaixo_do_limiar_so_registra_par():
    mapa, fusoes, pares = rz.agrupar(ITENS, {"tosse"}, VETORES, limiar=0.92)
    assert mapa["tosse_seca"] == "tosse_seca" and fusoes == []
    assert pares[0][:2] == ("tosse_seca", "tosse") and pares[0][2] == pytest.approx(0.9)


def test_agrupar_nunca_funde_dois_canonicos():
    v = {"a": [1.0, 0.0], "b": [1.0, 0.0]}
    mapa, fusoes, _ = rz.agrupar({"a": 1, "b": 1}, {"a", "b"}, v, limiar=0.5)
    assert mapa == {"a": "a", "b": "b"} and fusoes == []


def test_escolher_limiar():
    rot = [(0.95, True), (0.93, True), (0.91, False), (0.90, True)]
    assert rz.escolher_limiar(rot) == 0.93
    assert rz.escolher_limiar([(0.90, False)]) == rz.LIMIAR_PADRAO


def test_ler_rotulados(tmp_path):
    assert rz.ler_rotulados(tmp_path / "nao_existe.csv") is None
    arq = tmp_path / "pares.csv"
    arq.write_text("label,id_a,id_b,cosseno,mesmo\nX,a,b,0.9,s\nX,c,d,0.85,n\nX,e,f,0.82,\n")
    assert rz.ler_rotulados(arq) == [(0.9, True), (0.85, False)]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest -q tests/test_resolucao.py -k "agrupar or limiar or rotulados"`
Expected: FAIL com `AttributeError: ... has no attribute 'agrupar'`.

- [ ] **Step 3: Implementar**

Em `src/graphrag_bulas/resolucao.py`, acrescentar `import csv` no topo dos imports e, ao fim do arquivo:

```python
def _cos(a, b) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # vetores já normalizados


def agrupar(itens, canonicos, vetores, limiar):
    """Funde ids parecidos de um label. Devolve ({id: representante}, fusões, pares).

    itens: {id: frequência}; canonicos: ids do dicionário; vetores: {id: vetor normalizado}.
    Ordem: canônicos primeiro, depois os mais frequentes; cada id vai para o representante mais
    parecido já visto, se o cosseno passa do limiar e o par não é bloqueado. Dois canônicos
    nunca se fundem. fusões: [(de, para, cos)]; pares: [(id, representante, cos)] na FAIXA_PARES.
    """
    ordem = sorted(itens, key=lambda i: (i not in canonicos, -itens[i], i))
    mapa, reps, fusoes, pares = {}, [], [], []
    for i in ordem:
        melhor, cos = None, -1.0
        for r in reps:
            if bloqueado(i, r) or (i in canonicos and r in canonicos):
                continue
            c = _cos(vetores[i], vetores[r])
            if c > cos:
                melhor, cos = r, c
        if melhor and FAIXA_PARES[0] <= cos < FAIXA_PARES[1]:
            pares.append((i, melhor, cos))
        if melhor and cos >= limiar:
            mapa[i] = melhor
            fusoes.append((i, melhor, cos))
        else:
            mapa[i] = i
            reps.append(i)
    return mapa, fusoes, pares


def escolher_limiar(rotulados, alvo=0.95, padrao=LIMIAR_PADRAO) -> float:
    """Menor cosseno de corte com precisão >= alvo nos pares rotulados [(cos, mesmo)]."""
    for t in sorted({c for c, _ in rotulados}):
        acima = [m for c, m in rotulados if c >= t]
        if sum(acima) / len(acima) >= alvo:
            return t
    return padrao


def ler_rotulados(path: Path = ROTULADOS):
    if not path.exists():
        return None
    with path.open() as f:
        return [
            (float(r["cosseno"]), r["mesmo"].strip().lower() == "s")
            for r in csv.DictReader(f)
            if r["mesmo"].strip()
        ]
```

Nota: `_cos` em Python puro, sem numpy (numpy só vem com o extra `embeddings`). Com ~850 ids no maior label são poucos segundos.

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest -q tests/test_resolucao.py && uv run ruff check src tests`
Expected: 20 passed; `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add src/graphrag_bulas/resolucao.py tests/test_resolucao.py
git commit -m "feat: fusão de entidades por similaridade de embedding com limiar (E4.2)"
```

---

### Task 5: `resolver`, relatório da resolução e CLI

**Files:**
- Modify: `src/graphrag_bulas/resolucao.py`
- Test: `tests/test_resolucao.py`

**Interfaces:**
- Consumes: `normalizar`, `carregar_dicionario`, `agrupar`, `escolher_limiar`, `ler_rotulados`; `graphrag_bulas.embeddings.embed(textos) -> list[list[float]]` só no `main`.
- Produces:
  - `Resolucao` (dataclass): `nos: list[dict]`, `rels: list[dict]`, `antes: Counter`, `passos: Counter[(label, passo)]`, `fusoes: list[(label, de, para, cos)]`, `pares: list[(label, id, rep, cos)]`, `rels_antes: Counter`, `lacos: int`, `unicos: list[(label, id)]`.
  - `resolver(linhas, dicionario, embed, limiar) -> Resolucao`.
  - `relatorio(res: Resolucao, limiar: float, fonte_limiar: str) -> str`.
  - Formato das linhas de `grafo.jsonl` (usado na Task 6):
    - nó: `{"tipo": "no", "label", "id", "nome", "sinonimos": [str]}`
    - relação: `{"tipo": "rel", "rel", "label_origem", "origem", "label_destino", "destino", "frequencia", "gravidade", "efeito", "dose", "confianca", "fonte_chunk_id", "chunks": [str]}`

- [ ] **Step 1: Escrever os testes que falham** (acrescentar ao fim de `tests/test_resolucao.py`)

```python
def _ent(i, label, nome):
    return {"id": i, "label": label, "nome": nome}


def _rel(tipo, o, d, confianca, **kw):
    base = {"frequencia": None, "gravidade": None, "efeito": None, "dose": None}
    return {"tipo": tipo, "origem": o, "destino": d, "confianca": confianca, **base, **kw}


LINHAS = [
    {
        "chunk_id": "bula_cozaar_interacoes_0",
        "bula": "bula_cozaar",
        "entidades": [
            _ent("losartana", "PrincipioAtivo", "Losartana"),
            _ent("aines", "ClasseTerapeutica", "AINEs"),
        ],
        "relacoes": [_rel("INTERAGE_COM", "losartana", "aines", 0.7, gravidade="desconhecida")],
    },
    {
        "chunk_id": "bula_cozaar_interacoes_1",
        "bula": "bula_cozaar",
        "entidades": [
            _ent("losartana_potassica", "PrincipioAtivo", "Losartana potássica"),
            _ent(
                "anti_inflamatorios_nao_esteroides",
                "ClasseTerapeutica",
                "Anti-inflamatórios não esteroides",
            ),
        ],
        "relacoes": [
            _rel(
                "INTERAGE_COM",
                "losartana_potassica",
                "anti_inflamatorios_nao_esteroides",
                1.0,
                gravidade="grave",
            )
        ],
    },
    {
        "chunk_id": "bula_marevan_interacoes_0",
        "bula": "bula_marevan",
        "entidades": [
            _ent("varfarina", "PrincipioAtivo", "Varfarina"),
            _ent("varfarina_sodica", "PrincipioAtivo", "Varfarina sódica"),
        ],
        "relacoes": [_rel("INTERAGE_COM", "varfarina", "varfarina_sodica", 1.0)],
    },
]
DIC = {
    "ClasseTerapeutica": {"aine": "aine", "anti_inflamatorio_nao_esteroide": "aine"},
    "PrincipioAtivo": {"losartana": "losartana"},
}


def _embed_ortogonal(textos):
    """Um vetor por texto, todos ortogonais: o passo de embedding não funde nada."""
    return [[1.0 if j == i else 0.0 for j in range(len(textos))] for i in range(len(textos))]


def test_resolver_funde_entidades_e_junta_relacoes_repetidas():
    res = rz.resolver(LINHAS, DIC, _embed_ortogonal, limiar=0.92)
    assert len(res.rels) == 1
    r = res.rels[0]
    assert (r["rel"], r["label_origem"], r["origem"], r["label_destino"], r["destino"]) == (
        "INTERAGE_COM",
        "PrincipioAtivo",
        "losartana",
        "ClasseTerapeutica",
        "aine",
    )
    assert r["confianca"] == 1.0 and r["gravidade"] == "grave"
    assert r["fonte_chunk_id"] == "bula_cozaar_interacoes_1"
    assert r["chunks"] == ["bula_cozaar_interacoes_0", "bula_cozaar_interacoes_1"]
    assert res.lacos == 1  # varfarina -> varfarina_sodica vira laço
    aine = next(n for n in res.nos if n["id"] == "aine")
    assert aine["sinonimos"] and aine["nome"] not in aine["sinonimos"]
    assert res.antes["PrincipioAtivo"] == 4
    assert {n["id"] for n in res.nos if n["label"] == "PrincipioAtivo"} == {
        "losartana",
        "varfarina",
    }
    assert res.passos["ClasseTerapeutica", "dicionario"] == 1


def test_relatorio_tem_tabela_antes_depois():
    res = rz.resolver(LINHAS, DIC, _embed_ortogonal, limiar=0.92)
    texto = rz.relatorio(res, 0.92, "padrão")
    assert "| ClasseTerapeutica | 2 | 1 |" in texto
    assert "| INTERAGE_COM | 3 | 1 |" in texto
    assert "laço depois da fusão: 1" in texto
```

Atenção: o embedding falso precisa ser ortogonal. Um vetor constante faz todo id não canônico se fundir no primeiro representante (cosseno 1).

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest -q tests/test_resolucao.py -k "resolver or relatorio"`
Expected: FAIL com `AttributeError: ... has no attribute 'resolver'`.

- [ ] **Step 3: Implementar**

Em `src/graphrag_bulas/resolucao.py`, o bloco de imports fica:

```python
import csv
import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from graphrag_bulas.chunks import PROCESSADOS, slug
from graphrag_bulas.extracao import COMPOSICAO

log = logging.getLogger(__name__)
```

E acrescentar ao fim do arquivo:

```python
@dataclass
class Resolucao:
    nos: list[dict]
    rels: list[dict]
    antes: Counter
    passos: Counter = field(default_factory=Counter)  # (label, passo) -> ids fundidos
    fusoes: list = field(default_factory=list)  # (label, de, para, cos)
    pares: list = field(default_factory=list)  # (label, id, representante, cos)
    rels_antes: Counter = field(default_factory=Counter)
    lacos: int = 0
    unicos: list = field(default_factory=list)  # (label, id) visto 1 vez e sem fusão


def resolver(linhas, dicionario, embed, limiar) -> Resolucao:
    """Resolve as entidades de extracoes.jsonl e junta as relações repetidas.

    embed(textos) -> vetores normalizados (embeddings.embed nos scripts; falso nos testes).
    """
    freq, nomes = Counter(), defaultdict(Counter)
    for linha in linhas:
        for e in linha["entidades"]:
            freq[e["label"], e["id"]] += 1
            nomes[e["label"], e["id"]][e["nome"]] += 1
    antes = Counter(label for label, _ in freq)

    res = Resolucao(nos=[], rels=[], antes=antes)
    passo1 = {}
    for label, i in freq:
        n = normalizar(i, label)
        d = dicionario.get(label, {}).get(n, n)
        passo1[label, i] = d
        if n != i:
            res.passos[label, "regra"] += 1
        if d != n:
            res.passos[label, "dicionario"] += 1

    por_label = defaultdict(Counter)
    nomes2 = defaultdict(Counter)
    for (label, i), d in passo1.items():
        por_label[label][d] += freq[label, i]
        nomes2[label, d].update(nomes[label, i])

    final = {}
    for label, itens in por_label.items():
        if label in SEM_EMBEDDING:
            final.update({(label, d): d for d in itens})
            continue
        ids = sorted(itens)
        textos = [nomes2[label, d].most_common(1)[0][0] for d in ids]
        vetores = dict(zip(ids, embed(textos), strict=True))
        canonicos = set(dicionario.get(label, {}).values())
        mapa, fusoes, pares = agrupar(itens, canonicos, vetores, limiar)
        final.update({(label, d): r for d, r in mapa.items()})
        res.passos[label, "embedding"] += len(fusoes)
        res.fusoes += [(label, *f) for f in fusoes]
        res.pares += [(label, *p) for p in pares]
        fundidos = {f[0] for f in fusoes} | {f[1] for f in fusoes}
        res.unicos += [(label, d) for d in ids if itens[d] == 1 and d not in fundidos]

    agrupados = defaultdict(Counter)
    for (label, d), r in final.items():
        agrupados[label, r].update(nomes2[label, d])
    for (label, r), cont in sorted(agrupados.items()):
        nome = cont.most_common(1)[0][0]
        res.nos.append(
            {
                "tipo": "no",
                "label": label,
                "id": r,
                "nome": nome,
                "sinonimos": sorted(n for n in cont if n != nome),
            }
        )

    def mapear(label, i):
        return final[label, passo1[label, i]]

    rels = {}
    for linha in linhas:
        labels = {e["id"]: e["label"] for e in linha["entidades"]}
        for r in linha["relacoes"]:
            res.rels_antes[r["tipo"]] += 1
            lo, ld = labels[r["origem"]], labels[r["destino"]]
            o, d = mapear(lo, r["origem"]), mapear(ld, r["destino"])
            if (lo, o) == (ld, d):
                res.lacos += 1
                continue
            chave = (r["tipo"], lo, o, ld, d)
            props = {p: r.get(p) for p in ("frequencia", "gravidade", "efeito", "dose")}
            nova = {
                "tipo": "rel",
                "rel": r["tipo"],
                "label_origem": lo,
                "origem": o,
                "label_destino": ld,
                "destino": d,
                **props,
                "confianca": r["confianca"],
                "fonte_chunk_id": linha["chunk_id"],
                "chunks": [linha["chunk_id"]],
            }
            atual = rels.get(chave)
            if atual is None:
                rels[chave] = nova
                continue
            chunks = sorted({*atual["chunks"], linha["chunk_id"]})
            if nova["confianca"] > atual["confianca"]:
                rels[chave] = nova
            rels[chave]["chunks"] = chunks
    res.rels = list(rels.values())
    return res


def relatorio(res: Resolucao, limiar: float, fonte_limiar: str) -> str:
    depois = Counter(n["label"] for n in res.nos)
    rels_depois = Counter(r["rel"] for r in res.rels)
    linhas = [
        "# Relatório E4 — resolução e ingestão",
        "",
        f"Limiar de embedding: {limiar:.3f} ({fonte_limiar}).",
        "",
        "## Nós por label",
        "",
        "| Label | Antes | Depois | Regra | Dicionário | Embedding |",
        "|---|---|---|---|---|---|",
    ]
    for label in sorted(res.antes):
        linhas.append(
            f"| {label} | {res.antes[label]} | {depois[label]} | "
            f"{res.passos[label, 'regra']} | {res.passos[label, 'dicionario']} | "
            f"{res.passos[label, 'embedding']} |"
        )
    linhas += ["", "## Relações por tipo", "", "| Tipo | Antes | Depois |", "|---|---|---|"]
    for tipo in sorted(res.rels_antes):
        linhas.append(f"| {tipo} | {res.rels_antes[tipo]} | {rels_depois[tipo]} |")
    linhas += [
        "",
        f"Relações descartadas por laço depois da fusão: {res.lacos}.",
        "",
        "## 30 maiores fusões por embedding",
        "",
        "| Label | De | Para | Cosseno |",
        "|---|---|---|---|",
    ]
    for label, de, para, cos in sorted(res.fusoes, key=lambda f: -f[3])[:30]:
        linhas.append(f"| {label} | {de} | {para} | {cos:.3f} |")
    linhas += ["", f"## Ids vistos uma vez e sem fusão ({len(res.unicos)})", ""]
    linhas += [f"- {label}: {i}" for label, i in sorted(res.unicos)]
    return "\n".join(linhas) + "\n"


def main():
    from graphrag_bulas.embeddings import embed

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
    )
    linhas = [json.loads(x) for x in ENTRADA.open()]
    rotulados = ler_rotulados()
    if rotulados:
        limiar, fonte = escolher_limiar(rotulados), f"{len(rotulados)} pares rotulados"
    else:
        limiar, fonte = LIMIAR_PADRAO, "padrão; sem data/curadoria/pares_rotulados.csv"
        log.warning("sem pares rotulados: limiar padrão %.2f", limiar)
    res = resolver(linhas, carregar_dicionario(), embed, limiar)

    with SAIDA.open("w") as f:
        for item in [*res.nos, *res.rels]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    PARES.parent.mkdir(exist_ok=True)
    with PARES.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "id_a", "id_b", "cosseno", "mesmo"])
        for label, a, b, cos in sorted(res.pares, key=lambda p: -p[3]):
            w.writerow([label, a, b, f"{cos:.4f}", ""])
    RELATORIO.write_text(relatorio(res, limiar, fonte))
    print(
        f"{SAIDA.name}: {len(res.nos)} nós, {len(res.rels)} relações; "
        f"{len(res.pares)} pares candidatos; relatório em {RELATORIO}"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest -q tests/test_resolucao.py && uv run ruff check src tests && uv run ruff format --check src tests`
Expected: 22 passed; lint e format limpos.

- [ ] **Step 5: Rodar no corpus real**

Run: `uv run --extra embeddings python -m graphrag_bulas.resolucao`
Expected: na primeira vez baixa o bge-m3 (~2 GB). Termina com algo como `grafo.jsonl: ~1600 nós, ~2800 relações; N pares candidatos; relatório em .../logs/relatorio_e4.md` e o aviso `sem pares rotulados: limiar padrão 0.92`. Abrir `logs/relatorio_e4.md` e conferir a tabela "30 maiores fusões": nenhuma fusão de sentido oposto (ex.: `hipercalemia` → `hipocalemia`). Se houver, acrescentar o par de prefixos a `OPOSTOS` com um teste em `test_bloqueado` e rodar de novo.

- [ ] **Step 6: Commit**

```bash
git add src/graphrag_bulas/resolucao.py tests/test_resolucao.py
git commit -m "feat: resolução de entidades gera grafo.jsonl e relatório (E4.1, E4.2, E4.5)"
```

---

### Task 6: Linhas da ingestão (sem Neo4j)

**Files:**
- Create: `src/graphrag_bulas/ingestao.py`
- Test: `tests/test_ingestao.py`

**Interfaces:**
- Consumes: `resolucao.RAIZ`, `resolucao.SAIDA`, `resolucao.RELATORIO`, `resolucao.carregar_dicionario`; `chunks.bula_id(arquivo) -> str`, `chunks.slug`; `extracao.COMPOSICAO`; formato de `grafo.jsonl` (Task 5).
- Produces:
  - `statements(texto: str) -> list[str]`
  - `lotes(itens: list, n: int = 500)` (gerador)
  - `ler_grafo(path=SAIDA) -> tuple[list[dict], list[dict]]` — `(nos, rels)`
  - `linhas_bulas(manifesto: list[dict], bulas: set[str], dic_fabricante: dict[str, str]) -> list[dict]` com chaves `bula, med, nome, arquivo, registro, data (ISO), fab, fab_nome`
  - `linhas_chunks(chunks: list[dict], bulas: set[str]) -> list[dict]` com chaves `bula, secao, tipo, id, ordem, texto`
  - `linhas_composicao(nos: list[dict]) -> list[dict]` com chaves `med, pa, nome`
  - `linhas_menciona(rels: list[dict]) -> dict[str, list[dict]]` — label → `[{"id", "chunk"}]`
  - Constantes `CYPHER`, `MANIFESTO`, `URL_BULARIO`, `LOTE = 500`, `PROPS`.

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_ingestao.py`:

```python
"""Ingestão no Neo4j (E4.3, E4.4). Montagem das linhas sem banco; carga com a fixture db."""

from graphrag_bulas import ingestao as ig


def test_statements_ignora_comentario_e_ponto_e_virgula_dentro_de_string():
    texto = "// comentário; com ponto e vírgula\nCREATE (n {t: 'a; b'});\nMATCH (n) RETURN n;\n"
    assert ig.statements(texto) == ["CREATE (n {t: 'a; b'})", "MATCH (n) RETURN n"]


def test_statements_do_seed_e_do_schema():
    assert len(ig.statements((ig.CYPHER / "schema.cypher").read_text())) == 15
    assert len(ig.statements((ig.CYPHER / "seed.cypher").read_text())) == 17


MANIFESTO = [
    {
        "arquivo": "bula_cozaar.pdf",
        "medicamento": "COZAAR",
        "empresa": "Organon Farmacêutica Ltda.",
        "registro_ms": "1.0029.0007",
        "data_publicacao": "24/04/2025",
    },
    {
        "arquivo": "bula_Lipitor.pdf",
        "medicamento": "LIPITOR",
        "empresa": "Pfizer Brasil Ltda.",
        "registro_ms": "1.0216.0001",
        "data_publicacao": "01/01/2025",
    },
]


def test_linhas_bulas_filtra_escopo_e_resolve_fabricante():
    rows = ig.linhas_bulas(MANIFESTO, {"bula_cozaar"}, {"organon_farmaceutica_ltda": "organon"})
    assert rows == [
        {
            "bula": "bula_cozaar",
            "med": "cozaar",
            "nome": "Cozaar",
            "arquivo": "data/raw/bula_cozaar.pdf",
            "registro": "1.0029.0007",
            "data": "2025-04-24",
            "fab": "organon",
            "fab_nome": "Organon Farmacêutica Ltda.",
        }
    ]


def test_linhas_chunks_filtra_escopo():
    chunks = [
        {
            "id": "bula_cozaar_indicacoes_0",
            "bula": "bula_cozaar",
            "secao": "bula_cozaar_indicacoes",
            "tipo": "indicacoes",
            "ordem": 0,
            "texto": "t",
        },
        {
            "id": "bula_lipitor_indicacoes_0",
            "bula": "bula_lipitor",
            "secao": "bula_lipitor_indicacoes",
            "tipo": "indicacoes",
            "ordem": 0,
            "texto": "u",
        },
    ]
    assert [c["id"] for c in ig.linhas_chunks(chunks, {"bula_cozaar"})] == [
        "bula_cozaar_indicacoes_0"
    ]


def test_linhas_composicao_usa_nome_do_grafo_ou_id():
    rows = ig.linhas_composicao(
        [{"label": "PrincipioAtivo", "id": "losartana", "nome": "Losartana", "sinonimos": []}]
    )
    assert {"med": "cozaar", "pa": "losartana", "nome": "Losartana"} in rows
    assert {
        "med": "aspirina",
        "pa": "acido_acetilsalicilico",
        "nome": "Acido acetilsalicilico",
    } in rows


REL = {
    "rel": "INTERAGE_COM",
    "label_origem": "PrincipioAtivo",
    "origem": "losartana",
    "label_destino": "ClasseTerapeutica",
    "destino": "aine",
    "chunks": ["bula_cozaar_interacoes_0", "bula_cozaar_interacoes_1"],
}


def test_linhas_menciona_sem_repeticao():
    por_label = ig.linhas_menciona([REL, REL])
    assert por_label["PrincipioAtivo"] == [
        {"id": "losartana", "chunk": "bula_cozaar_interacoes_0"},
        {"id": "losartana", "chunk": "bula_cozaar_interacoes_1"},
    ]
    assert len(por_label["ClasseTerapeutica"]) == 2


def test_ler_grafo_separa_nos_e_relacoes(tmp_path):
    arq = tmp_path / "grafo.jsonl"
    arq.write_text('{"tipo": "no", "id": "a"}\n{"tipo": "rel", "rel": "X"}\n')
    nos, rels = ig.ler_grafo(arq)
    assert [n["id"] for n in nos] == ["a"] and [r["rel"] for r in rels] == ["X"]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest -q tests/test_ingestao.py`
Expected: FAIL com `ModuleNotFoundError: No module named 'graphrag_bulas.ingestao'`.

- [ ] **Step 3: Implementar**

`src/graphrag_bulas/ingestao.py`:

```python
"""Ingestão no Neo4j (E4.3, E4.4): grafo.jsonl + documentos -> Neo4j.

Uso:
  uv run --extra embeddings python -m graphrag_bulas.ingestao [--recriar]

Idempotente: só UNWIND + MERGE, em lotes. Aplica cypher/schema.cypher e cypher/seed.cypher,
carrega Bula/Secao/Chunk das bulas de extracoes.jsonl, CONTEM de extracao.COMPOSICAO, nós e
relações de grafo.jsonl, MENCIONA e embeddings. Acrescenta a parte da carga em
logs/relatorio_e4.md. Spec: docs/superpowers/specs/2026-11-01-e4-resolucao-ingestao-design.md
"""

import json
import re
from collections import defaultdict
from datetime import datetime

from graphrag_bulas.chunks import bula_id, slug
from graphrag_bulas.extracao import COMPOSICAO
from graphrag_bulas.resolucao import RAIZ, SAIDA

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
    for linha in path.open():
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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest -q tests/test_ingestao.py && uv run ruff check src tests && uv run ruff format --check src tests`
Expected: 7 passed; lint e format limpos.

- [ ] **Step 5: Commit**

```bash
git add src/graphrag_bulas/ingestao.py tests/test_ingestao.py
git commit -m "feat: monta as linhas da ingestão a partir de grafo.jsonl e do manifesto (E4.3)"
```

---

### Task 7: Carga no Neo4j, relatório da carga e CLI (E4.3, E4.4)

**Files:**
- Modify: `src/graphrag_bulas/ingestao.py`
- Test: `tests/test_ingestao.py`

**Interfaces:**
- Consumes: Task 6; `config.get_driver()`; `modelos.LABELS`, `modelos.RELACOES`; `embeddings.embed_missing(driver) -> dict` (só no `main`); `resolucao.RELATORIO`, `resolucao.carregar_dicionario`; fixture `db` de `tests/conftest.py`.
- Produces: `carregar_documentos(driver, bulas_rows, chunk_rows) -> list[str]` (ids de Chunk cujo texto mudou), `carregar_nos(driver, nos)`, `carregar_composicao(driver, rows)`, `carregar_rels(driver, rels)`, `carregar_menciona(driver, rels)`, `contar(driver) -> tuple[dict, dict]`, `relatorio_carga(alterados, nos_db, rels_db, nos, rels) -> str`, `main(argv=None)`.

- [ ] **Step 1: Escrever o teste que falha** (acrescentar ao fim de `tests/test_ingestao.py`)

```python
NOS_TESTE = [
    {
        "tipo": "no",
        "label": "PrincipioAtivo",
        "id": "zz_teste_pa",
        "nome": "ZZ PA",
        "sinonimos": ["zz pa sal"],
    },
    {
        "tipo": "no",
        "label": "ClasseTerapeutica",
        "id": "zz_teste_classe",
        "nome": "ZZ Classe",
        "sinonimos": [],
    },
]
RELS_TESTE = [
    {
        "tipo": "rel",
        "rel": "INTERAGE_COM",
        "label_origem": "PrincipioAtivo",
        "origem": "zz_teste_pa",
        "label_destino": "ClasseTerapeutica",
        "destino": "zz_teste_classe",
        "gravidade": "grave",
        "efeito": "x",
        "frequencia": None,
        "dose": None,
        "confianca": 0.7,
        "fonte_chunk_id": "zz_teste_chunk",
        "chunks": ["zz_teste_chunk"],
    },
    # Igual a uma relação do seed (metodo='manual'): a carga não pode trocar o método.
    {
        "tipo": "rel",
        "rel": "PERTENCE_A",
        "label_origem": "PrincipioAtivo",
        "origem": "ibuprofeno",
        "label_destino": "ClasseTerapeutica",
        "destino": "aine",
        "gravidade": None,
        "efeito": None,
        "frequencia": None,
        "dose": None,
        "confianca": 0.4,
        "fonte_chunk_id": "zz_teste_chunk",
        "chunks": [],
    },
]


def _carregar(db):
    ig.carregar_nos(db, NOS_TESTE)
    ig.carregar_rels(db, RELS_TESTE)
    ig.carregar_menciona(db, RELS_TESTE)


def test_carga_idempotente_e_preserva_seed(db):
    db.execute_query("MERGE (:Chunk {id: 'zz_teste_chunk', texto: 'zz'})")
    try:
        _carregar(db)
        _carregar(db)
        n = db.execute_query("""
            MATCH (p:PrincipioAtivo:Entidade {id: 'zz_teste_pa'})
            OPTIONAL MATCH (p)-[i:INTERAGE_COM]->(:ClasseTerapeutica {id: 'zz_teste_classe'})
            OPTIONAL MATCH (:Chunk {id: 'zz_teste_chunk'})-[m:MENCIONA]->(p)
            RETURN count(DISTINCT p) AS nos, count(DISTINCT i) AS rels, count(DISTINCT m) AS menc,
                   p.sinonimos AS sin, collect(i.metodo)[0] AS metodo
            """).records[0]
        assert (n["nos"], n["rels"], n["menc"]) == (1, 1, 1)
        assert n["sin"] == ["zz pa sal"] and n["metodo"] == "llm"
        seed = db.execute_query(
            "MATCH (:PrincipioAtivo {id: 'ibuprofeno'})-[x:PERTENCE_A]->(:ClasseTerapeutica "
            "{id: 'aine'}) RETURN count(x) AS n, collect(x.metodo) AS metodos"
        ).records[0]
        assert seed["n"] == 1 and seed["metodos"] == ["manual"]
    finally:
        db.execute_query("MATCH (n) WHERE n.id STARTS WITH 'zz_teste' DETACH DELETE n")


def test_relatorio_carga_compara_arquivo_e_banco():
    texto = ig.relatorio_carga(
        ["bula_cozaar_indicacoes_0"],
        {"PrincipioAtivo": 2},
        {"INTERAGE_COM": 1},
        [{"label": "PrincipioAtivo"}],
        [{"rel": "INTERAGE_COM"}],
    )
    assert "- bula_cozaar_indicacoes_0" in texto
    assert "| PrincipioAtivo | 1 | 2 |" in texto and "| INTERAGE_COM | 1 | 1 |" in texto
```

- [ ] **Step 2: Subir o Neo4j com o seed e ver falhar**

```bash
docker compose up -d
docker exec -i graphrag-neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" < cypher/schema.cypher
docker exec -i graphrag-neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" < cypher/seed.cypher
uv run pytest -q tests/test_ingestao.py
```
Expected: FAIL com `AttributeError: ... has no attribute 'carregar_nos'` e `... 'relatorio_carga'`. Se `test_carga_idempotente_e_preserva_seed` aparecer como skipped, o Neo4j ou o seed não estão de pé: resolver antes de seguir.

- [ ] **Step 3: Implementar**

Em `src/graphrag_bulas/ingestao.py`, o bloco de imports fica:

```python
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
```

E acrescentar ao fim do arquivo:

```python
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
        assert label in LABELS, label  # label entra na query por f-string
        _rodar(
            driver,
            f"""
            UNWIND $rows AS r
            MERGE (n:{label} {{id: r.id}})
            ON CREATE SET n:Entidade, n.nome = r.nome, n.sinonimos = []
            SET n.sinonimos = n.sinonimos + [s IN r.sinonimos WHERE NOT s IN n.sinonimos]
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
        assert rel in RELACOES and lo in LABELS and ld in LABELS, (rel, lo, ld)
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
        assert label in LABELS, label
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
    bulas = {json.loads(x)["bula"] for x in (PROCESSADOS / "extracoes.jsonl").open()}
    chunks = [json.loads(x) for x in (PROCESSADOS / "chunks.jsonl").open()]
    manifesto = [json.loads(x) for x in MANIFESTO.open()]
    dic_fab = carregar_dicionario().get("Fabricante", {})

    with get_driver() as driver:
        driver.verify_connectivity()  # Neo4j fora do ar: para aqui com o erro do driver
        if a.recriar:
            driver.execute_query("MATCH (n) DETACH DELETE n")
        for arq in ("schema.cypher", "seed.cypher"):
            for s in statements((CYPHER / arq).read_text()):
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

    with RELATORIO.open("a") as f:
        f.write(relatorio_carga(alterados, nos_db, rels_db, nos, rels))
    print(f"nós: {nos_db}\nrelações: {rels_db}")


if __name__ == "__main__":
    main()
```

Notas:
- A ordem de `main` segue a spec: schema e seed primeiro, então o seed define `nome` e as relações manuais; o LLM só cria o que falta (`ON CREATE SET`).
- `SET ch.embedding = CASE ...` antes de `SET ch.texto`: chunk cujo texto mudou perde o embedding antigo e o `embed_missing` recalcula.
- `FABRICADO_POR` e `CONTEM` sem `fonte_chunk_id`: propriedade ausente equivale a nula no Neo4j.

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest -q tests/test_ingestao.py && uv run ruff check src tests && uv run ruff format --check src tests`
Expected: 9 passed (nenhum skipped com o Neo4j de pé); lint e format limpos.

- [ ] **Step 5: Commit**

```bash
git add src/graphrag_bulas/ingestao.py tests/test_ingestao.py
git commit -m "feat: ingestão idempotente no Neo4j com MENCIONA, embeddings e relatório (E4.3, E4.4)"
```

---

### Task 8: Carga do corpus, ajuste dos testes que supõem só o seed e README

**Files:**
- Modify: testes com a fixture `db` que falharem (lista abaixo), `README.md`

**Interfaces:**
- Consumes: CLIs das Tasks 5 e 7.
- Produces: grafo completo no Neo4j; `logs/relatorio_e4.md` completo.

- [ ] **Step 1: Rodar a carga**

```bash
uv run --extra embeddings python -m graphrag_bulas.resolucao
uv run --extra embeddings python -m graphrag_bulas.ingestao --recriar
```
Expected: no fim, `nós: {...}` e `relações: {...}`. Em `logs/relatorio_e4.md`, a tabela "Carga no Neo4j" deve ter, para cada label de entidade, Neo4j ≥ grafo.jsonl (o seed soma nós). Se Neo4j < grafo.jsonl em algum label ou relação, há `MATCH` sem par: parar e investigar antes de seguir.

- [ ] **Step 2: Rodar a carga de novo, sem `--recriar`, e conferir idempotência**

Run: `uv run --extra embeddings python -m graphrag_bulas.ingestao`
Expected: as mesmas contagens do Step 1 e `embeddings: {'Entidade': 0, 'Chunk': 0}`.

- [ ] **Step 3: Rodar a suíte inteira com o grafo completo**

Run: `uv run pytest -q`
Expected: podem falhar testes de `tests/test_seed.py`, `tests/test_retrieval.py`, `tests/test_gds.py`, `tests/test_text2cypher.py`, `tests/test_api.py`, `tests/test_contexto.py`, `tests/test_rag_vetorial.py`, `tests/test_embeddings.py` que comparam com `==` resultados do grafo semente.

- [ ] **Step 4: Ajustar cada teste que falhou, com estas regras**

Regra 1 — teste que verifica um fato do seed: restringir a consulta à camada manual com `WHERE r.metodo = 'manual'`, mantendo o `==`. Exemplo em `tests/test_seed.py`:

```python
def test_indicados_para_hipertensao(db):
    rows = consulta(
        db,
        "MATCH (m:Medicamento)-[r:INDICADO_PARA]->(:Condicao {id: 'hipertensao'}) "
        "WHERE r.metodo = 'manual' RETURN m.id AS id",
    )
    assert {r["id"] for r in rows} == {"cozaar", "renitec"}
```

Regra 2 — teste de retrieval, GDS, Text2Cypher ou API que compara o conjunto inteiro devolvido: trocar `==` por inclusão (`<=`) do que o seed garante. O grafo completo só pode trazer mais fatos. Exemplo:

```python
assert {"varfarina", "aine"} <= ids  # antes: assert ids == {"varfarina", "aine"}
```

Regra 3 — nunca apagar uma asserção nem marcar `skip`. Se um teste falhar porque o resultado do seed sumiu (não porque vieram fatos a mais), é bug da carga: voltar à Task 7.

Depois de cada arquivo ajustado:

Run: `uv run pytest -q <arquivo>`
Expected: passa.

- [ ] **Step 5: Documentar no README**

Acrescentar em `README.md`, depois da seção que aplica `cypher/schema.cypher` e `cypher/seed.cypher`:

````markdown
### Grafo completo (E4)

Depois da extração (E3.4), resolva as entidades e carregue no Neo4j:

```bash
uv run --extra embeddings python -m graphrag_bulas.resolucao   # extracoes.jsonl -> grafo.jsonl
uv run --extra embeddings python -m graphrag_bulas.ingestao --recriar
```

A ingestão aplica schema e seed, então não precisa rodar o `cypher-shell` antes. O relatório
de antes e depois (E4.5) fica em `logs/relatorio_e4.md`. Para documentar o limiar de fusão,
marque `s`/`n` na coluna `mesmo` de `logs/pares_candidatos.csv`, salve como
`data/curadoria/pares_rotulados.csv` e rode as duas etapas de novo.
````

- [ ] **Step 6: Verificação final**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check src tests`
Expected: tudo passa, nenhum skip por falta de Neo4j; lint e format limpos.

- [ ] **Step 7: Commit**

```bash
git add README.md tests/
git commit -m "test: ajusta testes ao grafo completo e documenta a ingestão do E4"
```

---

## Cobertura da spec

| Spec | Task |
|---|---|
| Normalização por regra (grafia, sal, singular de classe) | 2 |
| Dicionário curado com seed e nomes comerciais | 3 |
| Embedding com limiar, bloqueio de opostos, canônicos não se fundem | 4 |
| Pares candidatos e limiar a partir de pares rotulados (padrão 0,92) | 4, 5 |
| `grafo.jsonl` com relações repetidas juntadas pela maior confiança | 5 |
| Relatório da resolução (nós, relações, laços, fusões, ids únicos) | 5 |
| Schema e seed antes da carga; documentos das 25 bulas com manifesto | 7 |
| `CONTEM` de `COMPOSICAO`, `FABRICADO_POR` | 7 |
| Nós com `ON CREATE SET nome` e união de sinônimos | 7 |
| Relações com `ON CREATE SET`, seed preservado | 7 |
| `MENCIONA`, embeddings, `--recriar` | 7 |
| Relatório da carga (chunks do seed alterados, contagens no Neo4j) | 7 |
| Neo4j fora do ar para com erro claro | 7 (`verify_connectivity`) |
| Testes sem Neo4j e com Neo4j | 2–7 |
| Carga real e testes antigos com o grafo completo | 8 |
