# GraphRAG/KAG sobre bulas de medicamentos

Sistema de perguntas e respostas sobre bulas, com grafo de conhecimento no Neo4j e LLM (Gemini).
Responde em dois modos, mostrados lado a lado: GraphRAG (grafo multi-hop) e RAG tradicional
(só busca vetorial). Design: [`docs/superpowers/specs/2026-10-23-visao-graphrag-vs-rag-design.md`](docs/superpowers/specs/2026-10-23-visao-graphrag-vs-rag-design.md).
Planejamento da equipe: [`planejamento/PLANO_EQUIPE.md`](planejamento/PLANO_EQUIPE.md).

## Setup

Requisitos: [uv](https://docs.astral.sh/uv/), Docker.

```bash
cp .env.example .env          # preencha NEO4J_PASSWORD e GOOGLE_API_KEY
uv sync                       # cria .venv e instala dependências
uv sync --extra embeddings    # só quem trabalha com embeddings (instala torch)
docker compose up -d          # Neo4j 5 + APOC + GDS em http://localhost:7474
uv run python scripts/check_setup.py
```

Chave do Gemini (grátis): https://aistudio.google.com/apikey

## Corpus

PDFs das bulas em `data/raw/` (precisa do `pdftotext`, do poppler: `brew install poppler`):

```bash
uv run python scripts/gerar_manifesto.py   # metadados -> data/raw/manifesto.jsonl (E2.2)
uv run python -m graphrag_bulas.secoes     # texto por seção -> data/processed/secoes.jsonl (E2.3)
uv run python -m graphrag_bulas.chunks     # chunks com ID estável -> data/processed/chunks.jsonl (E2.4)
uv run python -m graphrag_bulas.extracao_corpus --bulas 10   # piloto da extração por LLM (E3.4)
uv run python -m graphrag_bulas.extracao_corpus              # corpus inteiro -> data/processed/extracoes.jsonl
```

A extração guarda cada resposta do LLM em `data/processed/cache_llm/`. Rodar de novo só chama o LLM
para chunks novos, que falharam ou cujo prompt mudou. `--max-chamadas N` limita o gasto da rodada.
`--pausa S` espaça as chamadas para respeitar o limite por minuto do plano grátis. `--modelo X`
troca o modelo só da extração (ex.: `gemini-3.5-flash-lite` quando o flash está sobrecarregado).

## Banco de dados

Schema documentado em [`docs/modelagem.md`](docs/modelagem.md). Para criar constraints e índices
(pode rodar de novo sem erro):

```bash
set -a; . ./.env; set +a
docker exec -i graphrag-neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" < cypher/schema.cypher
docker exec -i graphrag-neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" < cypher/seed.cypher
uv run python -m graphrag_bulas.embeddings   # grava embeddings que faltam (precisa --extra embeddings)
uv run pytest tests/test_seed.py   # confere as perguntas-alvo no grafo semente
```

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

Retrieval do GraphRAG (E5.1 + E5.2 + E5.3), pergunta → seeds → subgrafo + trechos + Cypher
gerado pelo Gemini (sem `llm=`, roda só a expansão):

    uv run python -c "from graphrag_bulas.config import get_driver, get_llm; from graphrag_bulas.retrieval import recuperar; import json; print(json.dumps(recuperar(get_driver(), 'Posso tomar Marevan com Advil?', llm=get_llm(temperature=0)), ensure_ascii=False, indent=2))"

Resposta completa (E5.5 + E5.6 + E5.7), com citações, confiança e recusa:

    uv run python -c "from graphrag_bulas.api import responder; import json; print(json.dumps(responder('Posso tomar Marevan com Advil?'), ensure_ascii=False, indent=2))"

Mesma pergunta no RAG tradicional (E5.8), só busca vetorial, sem grafo:

    uv run python -c "from graphrag_bulas.api import responder; import json; print(json.dumps(responder('Posso tomar Marevan com Advil?', modo='rag'), ensure_ascii=False, indent=2))"

O grafo semente (`cypher/seed.cypher`) tem 5 bulas (Cozaar, Renitec, Marevan, Advil, Aspirina)
e serve para começar retrieval e UI antes da ingestão completa.

## Estrutura

```
src/graphrag_bulas/   código do sistema (config.py: conexões Neo4j e LLM)
data/raw/             PDFs das bulas (fora do git)
data/processed/       texto/chunks JSONL (fora do git)
scripts/              utilitários de linha de comando
tests/                pytest
docs/                 modelagem, artigo
```

## Fluxo de trabalho

- `main` protegida: só entra por pull request com CI verde e 1 revisão.
- Branch por tarefa do plano: `<epico>/<id>-<descricao>`, ex.: `e3/e3.2-prompt-extracao`.
- Commits no formato `tipo: descrição` (`feat`, `fix`, `docs`, `test`, `refactor`, `chore`).
- Antes do PR: `uv run ruff format . && uv run ruff check . && uv run pytest`.

## Créditos

Frameworks open source usados: Neo4j, LangChain, sentence-transformers.
