# E7 — Avaliação GraphRAG vs baselines — design

Data: 2026-11-02. Status: aprovado.

## Objetivo

Medir o GraphRAG contra dois baselines com as mesmas perguntas, o mesmo LLM e os mesmos dados:

- `graphrag`: `responder(pergunta, "graphrag")` (E5.7).
- `rag`: `responder(pergunta, "rag")` (E5.8), só busca vetorial.
- `llm_puro`: o mesmo LLM, sem contexto.

Os números vão para o artigo (E8.3). O corpus fica fixo nas 25 bulas já extraídas.

## Decisões

| Tema | Decisão | Motivo |
|---|---|---|
| Julgamento | Fatos-chave por casamento de texto, sem LLM juiz | Reproduzível e barato. Um juiz qwen 7B seria fraco e julgaria a si mesmo. |
| Autor das perguntas | Claude, a partir do texto das bulas (não do grafo) | A equipe não tem especialista. Partir do texto evita favorecer a extração. Sem revisão humana: limitação declarada no artigo. |
| Gráficos | Fora. Só tabelas markdown | O artigo cabe com tabelas. Gráfico entra depois se o artigo pedir. |

## Gold de perguntas (E7.1)

Arquivo `data/gold/perguntas.json`, com `anotador` e uma lista `perguntas`. São 40 perguntas:

- 15 do tipo `1hop`: um fato de uma bula ("O Cozaar pode causar tontura?").
- 15 do tipo `multihop`: precisa ligar dois ou mais fatos ou bulas ("Quais AINEs do corpus interagem
  com a varfarina?").
- 10 do tipo `sem_resposta`: o assunto não está nas 25 bulas (medicamento fora do corpus, dado que a
  bula não traz).

```json
{
  "id": "q01",
  "tipo": "1hop",
  "pergunta": "O Cozaar pode causar tontura?",
  "fatos": [["tontura"]],
  "fontes": ["bula_cozaar_reacoes_adversas_0"]
}
```

- `fatos` é uma lista de fatos. Cada fato é uma lista de variantes aceitas (`["hemorragia",
  "sangramento"]`). Ficam vazios em `sem_resposta`.
- `fontes` são chunk_ids de `data/processed/chunks.jsonl` que sustentam a resposta. Ficam vazias
  em `sem_resposta`.
- `python -m graphrag_bulas.avaliacao validar` confere ids únicos, as contagens por tipo, que
  toda fonte existe nos chunks e que `1hop`/`multihop` têm fatos e fontes.

## Modo `llm_puro` (E7.3)

Em `avaliacao.py`, função `responder_llm_puro(llm, pergunta)`. Ela usa o mesmo modelo
`geracao.Resposta` (structured output) com um prompt sem contexto: "responda com o seu
conhecimento; se não souber, `suporte` = nenhum". Devolve as mesmas chaves que importam do
`responder()`: `resposta`, `recusou` (`suporte == "nenhum"`), `confianca` e `trechos` = [].

## Runner

`python -m graphrag_bulas.avaliacao rodar [--modo graphrag|rag|llm_puro]` roda cada pergunta em
cada modo e acrescenta uma linha por resposta em `logs/e7/respostas.jsonl`:
`{id, modo, resposta, recusou, confianca, citados, erro, segundos}`. `citados` são os chunk_ids
dos trechos com `citado: true`.

- Retomável: pula o par (id, modo) que já tem linha sem `erro`.
- Exceção numa pergunta grava `erro` e segue para a próxima.
- Um driver Neo4j e um LLM (`get_llm(temperature=0)`) para a rodada inteira.

## Métricas (E7.4)

Comparação de texto com `slug()` dos dois lados (minúsculas, sem acento, `_` no lugar de espaço),
procurando a variante como substring da resposta.

Para `1hop` e `multihop`:

- **cobertura**: fração dos fatos presentes na resposta. Resposta recusada vale 0.
- **acerto**: 1 se todos os fatos estão presentes.
- **recusa falsa**: 1 se recusou.
- **fidelidade**: fração dos `citados` que estão em `fontes`. Indefinida (fora da média) se não
  citou nada. Não existe para `llm_puro`.

Para `sem_resposta`:

- **recusa correta**: 1 se recusou.
- **alucinação**: 1 se respondeu (= 1 − recusa correta).

Linhas com `erro` ficam fora das médias e aparecem numa contagem própria.

## Relatório (E7.5)

`python -m graphrag_bulas.avaliacao relatorio` grava `logs/avaliacao_e7.md` com:

1. Tabela geral: modo × (cobertura, acerto, fidelidade, recusa falsa, recusa correta,
   alucinação, tempo médio, erros).
2. Tabela de cobertura e acerto por modo × tipo (`1hop`, `multihop`).
3. Aviso de que as perguntas não tiveram revisão humana.

## Testes

`tests/test_avaliacao.py`, sem Neo4j e sem LLM:

- casamento de fatos (acento, maiúscula, variante, resposta recusada);
- métricas de cada tipo com respostas fixas, incluindo fidelidade indefinida e linhas com erro;
- `validar` aceita um gold mínimo e rejeita fonte inexistente;
- `rodar` com responder falso grava as linhas, retoma sem repetir e registra exceção em `erro`;
- `responder_llm_puro` com LLM falso devolve `recusou` certo.

## Fora do escopo

- LLM juiz, revisão médica das perguntas, gráficos.
- As 28 bulas ainda não extraídas.
