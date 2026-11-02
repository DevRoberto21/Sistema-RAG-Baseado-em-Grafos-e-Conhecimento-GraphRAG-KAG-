# E6 — Interface — design

Data: 2026-11-02. Status: aprovado no chat.

## Objetivo

App Streamlit (`app/streamlit_app.py`) que manda a mesma pergunta para `responder(..., "graphrag")`
e `responder(..., "rag")` e mostra as duas respostas lado a lado (E6.2–E6.7).

## Tela

- Título em serifa, campo de pergunta e botão. Sem o cabeçalho e o rodapé do Streamlit.
- Duas colunas, GraphRAG e RAG tradicional. Cada uma mostra a resposta com uma etiqueta de
  confiança (ou "sem base nas bulas" quando recusa), os trechos com a bula de origem e o tempo.
- Na coluna GraphRAG: o subgrafo interativo (pyvis), com cor por label e tamanho por PageRank, o
  Cypher gerado e só os trechos citados. Na coluna RAG: os top-k trechos com a similaridade.
- Se um modo falhar, a coluna dele mostra o erro e a outra segue.
- Histórico da sessão: a última pergunta fica aberta e as anteriores viram uma lista recolhível.
- Aviso fixo: "não substitui a orientação de médico ou farmacêutico".

## Visual

Minimalista, no estilo Apple: fundo off-white `#FBFBFA`, texto em carvão, bordas de 1px `#EAEAEA`,
cantos de 12px, fonte do sistema (SF Pro) e serifa Newsreader no título, e cores pastel só nas
etiquetas e nos nós. As animações usam só `transform` e `opacity`: entrada dos cartões em cascata
(600ms, `cubic-bezier(0.16, 1, 0.3, 1)`), sombra leve no hover e uma mancha de luz que deriva
devagar no fundo.

## Código

- `src/graphrag_bulas/interface.py`: CSS e funções que devolvem HTML (cartões, trechos, Cypher,
  subgrafo). Escapa todo texto que vem do LLM ou das bulas.
- `app/streamlit_app.py`: só monta a página. Driver e LLM em `st.cache_resource`.
- Dependências no extra `ui` (streamlit, pyvis).

## Testes

`tests/test_interface.py` (pula sem o extra `ui`): escape de HTML, filtro de trechos citados,
subgrafo com nós e arestas e, com `AppTest`, os dois modos na tela com um deles falhando.

## Fora do escopo

Mock do contrato (E6.1), porque o backend real já existe. Seletor de um modo só.
