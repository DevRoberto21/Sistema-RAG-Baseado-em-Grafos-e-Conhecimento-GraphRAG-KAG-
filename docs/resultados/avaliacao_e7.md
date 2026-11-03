# Avaliação GraphRAG vs baselines (E7)

**Perguntas sem revisão humana** (escritas pelo Claude a partir das bulas). 40 perguntas.

## Geral
| modo | cobertura | acerto | fidelidade | recusa_falsa | recusa_correta | alucinacao | tempo médio (s) | erros |
|---|---|---|---|---|---|---|---|---|
| graphrag | 0.710 | 0.586 | 0.649 | 0.034 | 0.875 | 0.125 | 97.7 | 3 |
| rag | 0.699 | 0.567 | 0.595 | 0.033 | 1.000 | 0.000 | 31.6 | 0 |
| llm_puro | 0.368 | 0.259 | — | 0.037 | 0.100 | 0.900 | 40.8 | 3 |

## Por tipo
| modo | tipo | cobertura | acerto |
|---|---|---|---|
| graphrag | 1hop | 0.929 | 0.929 |
| graphrag | multihop | 0.506 | 0.267 |
| rag | 1hop | 1.000 | 1.000 |
| rag | multihop | 0.398 | 0.133 |
| llm_puro | 1hop | 0.564 | 0.462 |
| llm_puro | multihop | 0.185 | 0.071 |

## Notas da rodada (2026-11-03)

- Modos `graphrag` e `rag` rodados de novo depois dos commits fb0ec50 e d278f10. O `llm_puro`
  não usa citação e manteve as respostas de 2026-11-02.
- Causa das recusas falsas: o modelo citava o trecho como `[chunk_id]` (com os colchetes do
  contexto) ou copiava a linha inteira do fato; a citação era descartada e a resposta virava
  recusa. Recusa falsa caiu de 0.414 para 0.034 (GraphRAG) e de 0.467 para 0.033 (RAG).
- A única "alucinação" do GraphRAG (s02, Viagra e nitratos) é uma resposta que diz não haver
  informação, mas sem marcar `suporte: nenhum`, então não conta como recusa.
- Erros (JSON quebrado do qwen): q07, s05, s09, os mesmos de antes.
- Text-to-Cypher: 5 consultas falharam no `EXPLAIN` com `Variable r not defined`.

## Notas da rodada anterior (2026-11-02)

- LLM: Ollama `qwen2.5:7b`, temperatura 0, `num_ctx` 8192. Corpus: 25 bulas.
- Erros = o modelo devolveu JSON quebrado (repete uma frase até o limite de saída) e ficam fora das
  médias. GraphRAG: q07, s05, s09. LLM puro: 3 perguntas.
- Uma primeira rodada do GraphRAG, antes do corte do contexto em 16 mil caracteres (commit
  d6add5e), deu acerto 0.074 e recusa falsa 0.889: o contexto passava da janela do Ollama.
- `alucinacao` só mede as 10 perguntas sem resposta no corpus.
