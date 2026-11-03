# Avaliação GraphRAG vs baselines (E7)

**Perguntas sem revisão humana** (escritas pelo Claude a partir das bulas). 40 perguntas.

## Geral
| modo | cobertura | acerto | fidelidade | recusa_falsa | recusa_correta | alucinacao | tempo médio (s) | erros |
|---|---|---|---|---|---|---|---|---|
| graphrag | 0.737 | 0.600 | 0.713 | 0.033 | 1.000 | 0.000 | 122.0 | 0 |
| rag | 0.699 | 0.567 | 0.634 | 0.067 | 1.000 | 0.000 | 47.5 | 0 |
| llm_puro | 0.390 | 0.286 | — | 0.036 | 0.100 | 0.900 | 43.5 | 2 |

## Por tipo
| modo | tipo | cobertura | acerto |
|---|---|---|---|
| graphrag | 1hop | 0.900 | 0.867 |
| graphrag | multihop | 0.573 | 0.333 |
| rag | 1hop | 1.000 | 1.000 |
| rag | multihop | 0.398 | 0.133 |
| llm_puro | 1hop | 0.595 | 0.500 |
| llm_puro | multihop | 0.185 | 0.071 |

## Notas da rodada final (2026-11-03, tarde)

- GraphRAG rodado depois dos commits 69c76a9 e cc3bb42. RAG rodado depois de 69c76a9 (cc3bb42 não
  muda o modo rag). LLM puro: só as perguntas com erro foram refeitas; 2 seguem com JSON quebrado.
- Mudanças: `suporte` antes das listas e teto de itens no schema da Resposta (fim do JSON
  quebrado do GraphRAG: 3 erros -> 0); resposta que diz que o contexto não informa vira recusa
  (s02); fato do grafo sem trecho (ex.: CONTEM) sustenta a resposta (m06); o código nomeia a
  relação `r` quando o Cypher do modelo esquece.
- Falhas de Text-to-Cypher: 13 -> 8 (3 sem_consulta, 4 sintaxe, 1 `Variable r not defined`).
- Tempo médio do GraphRAG (122 s) e do RAG (47.5 s) inflado: a máquina rodou outras tarefas ao
  mesmo tempo. Na rodada de 2026-11-02 foram 99 s e 28 s.
- Variação entre rodadas com temperatura 0 é de 1 a 2 perguntas (ex.: q03 e m10 mudaram sem
  mudança de código que as afetasse).

## Notas da rodada intermediária (2026-11-03, manhã)

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
