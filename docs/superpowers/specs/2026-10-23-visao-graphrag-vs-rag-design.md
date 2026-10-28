# Visão GraphRAG vs RAG tradicional — design

Data: 2026-10-23. Status: aprovado.

## Objetivo

O sistema responde à mesma pergunta de dois jeitos e mostra os dois lado a lado:

- **GraphRAG**: busca vetorial + expansão multi-hop no grafo + GDS (épico E5).
- **RAG tradicional**: só busca vetorial nos trechos de bula (`Chunk`). Não percorre o grafo.

A comparação serve para a demo, para a avaliação (E7) e para o artigo (E8).
Ela só é justa se as duas respostas usarem o mesmo modelo, o mesmo prompt e os mesmos dados.
A única diferença entre os modos é o retrieval.

## Contrato da API

Uma função para os dois modos (estende o E5.7):

```python
responder(pergunta: str, modo: str = "graphrag") -> dict   # modo: "graphrag" | "rag"
```

Retorno, igual nos dois modos:

```json
{
  "modo": "graphrag",
  "resposta": "...",
  "subgrafo": {"nos": [...], "arestas": [...]},
  "cypher": "MATCH ...",
  "nos": ["..."],
  "confianca": 0.86,
  "recusou": false,
  "trechos": [{"chunk_id": "...", "texto": "...", "fonte": "...", "score": 0.81, "citado": true}]
}
```

`recusou` e `trechos[].citado` vieram do E5.6/E5.7 (`2026-10-28-e5-contexto-geracao-api-design.md`).
`trechos` são os trechos que entraram no contexto; `citado` marca os que a resposta cita.
No modo `graphrag`, cada item de `subgrafo.nos[]` tem `pagerank` (float ou `null`) e `comunidade`
(int ou `null`), calculados pelo GDS (`2026-10-28-e5-gds-modo-rag-design.md`).

No modo `rag`:

- `subgrafo` é `{"nos": [], "arestas": []}`, `cypher` é `null` e `nos` é `[]`.
- `trechos` vem ordenado por `score` (similaridade de cosseno), do maior para o menor.

Um modo desconhecido levanta `ValueError`.

## RAG tradicional

Módulo novo: `src/graphrag_bulas/rag_vetorial.py`.

1. Gera o embedding da pergunta com `embed()` (bge-m3, já existe). O bge-m3 não usa prefixo de query.
2. Busca os top-k no índice `chunk_embedding`, que já está em `cypher/schema.cypher`:
   `CALL db.index.vector.queryNodes('chunk_embedding', $k, $vetor)`. O padrão é k = 5.
3. Monta o contexto só com o texto dos chunks e a fonte de cada um.
4. Gera a resposta com a mesma função de geração do E5.6: cita os trechos, recusa quando o
   contexto não sustenta a resposta e dá um score de confiança.

O modo `rag` não usa `Entidade`, relações, Text-to-Cypher nem GDS.

## Interface

A UI (E6) manda a pergunta para os dois modos e mostra duas colunas:

| GraphRAG | RAG tradicional |
|---|---|
| resposta | resposta |
| subgrafo interativo + Cypher gerado | top-k trechos com score de similaridade |
| confiança | confiança |
| trechos citados | — |

Se um modo falhar, a coluna dele mostra o erro e a outra coluna continua a funcionar.

## Avaliação

- O baseline "RAG só vetorial" do E7.3 passa a chamar `responder(..., modo="rag")`.
  Não existe uma segunda implementação.
- O baseline "LLM puro" não muda.
- O E7.4 roda o gold set (E7.1) nos dois modos e compara acurácia, fidelidade às fontes,
  taxa de alucinação e taxa de recusa correta.

## Testes

Os testes usam o grafo semente e pulam sem Neo4j, como `tests/test_seed.py`.

- `modo="rag"` devolve `trechos` ordenados por `score` e `subgrafo` vazio.
- O retorno tem as mesmas chaves nos dois modos.
- Um modo inválido levanta `ValueError`.

## Mudanças no plano

- **E5.8 (novo, P5)**: modo `rag` no `responder()`. Depende de E5.6 e E5.7.
- **E6.1**: o contrato ganha o campo `modo`, e o mock cobre os dois modos.
- **E6.7 (novo, P6)**: visão lado a lado. Depende de E6.3, E6.4 e E5.8.
- **E7.3**: o baseline RAG reutiliza o E5.8.

## Fora do escopo

- Seletor de modo único na UI. A visão lado a lado já cobre esse caso.
- Busca híbrida (fulltext + vetor) no modo `rag`. O baseline usa só vetor, para isolar o ganho do grafo.
