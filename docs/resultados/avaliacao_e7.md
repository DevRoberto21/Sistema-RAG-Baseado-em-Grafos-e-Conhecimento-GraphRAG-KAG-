# Avaliação GraphRAG vs baselines (E7)

**Perguntas sem revisão humana** (escritas pelo Claude a partir das bulas). 40 perguntas.

## Geral
| modo | cobertura | acerto | fidelidade | recusa_falsa | recusa_correta | alucinacao | tempo médio (s) | erros |
|---|---|---|---|---|---|---|---|---|
| graphrag | 0.454 | 0.414 | 0.736 | 0.414 | 1.000 | 0.000 | 99.0 | 3 |
| rag | 0.439 | 0.400 | 0.531 | 0.467 | 1.000 | 0.000 | 27.6 | 0 |
| llm_puro | 0.368 | 0.259 | — | 0.037 | 0.100 | 0.900 | 40.8 | 3 |

## Por tipo
| modo | tipo | cobertura | acerto |
|---|---|---|---|
| graphrag | 1hop | 0.714 | 0.714 |
| graphrag | multihop | 0.211 | 0.133 |
| rag | 1hop | 0.667 | 0.667 |
| rag | multihop | 0.211 | 0.133 |
| llm_puro | 1hop | 0.564 | 0.462 |
| llm_puro | multihop | 0.185 | 0.071 |

## Notas da rodada (2026-11-02)

- LLM: Ollama `qwen2.5:7b`, temperatura 0, `num_ctx` 8192. Corpus: 25 bulas.
- Erros = o modelo devolveu JSON quebrado (repete uma frase até o limite de saída) e ficam fora das
  médias. GraphRAG: q07, s05, s09. LLM puro: 3 perguntas.
- Uma primeira rodada do GraphRAG, antes do corte do contexto em 16 mil caracteres (commit
  d6add5e), deu acerto 0.074 e recusa falsa 0.889: o contexto passava da janela do Ollama.
- `alucinacao` só mede as 10 perguntas sem resposta no corpus.
