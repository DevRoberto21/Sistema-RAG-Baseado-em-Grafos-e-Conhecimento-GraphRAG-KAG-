# GraphRAG/KAG sobre bulas de medicamentos

Sistema de perguntas e respostas sobre bulas, com grafo de conhecimento no Neo4j e LLM (Gemini).
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
