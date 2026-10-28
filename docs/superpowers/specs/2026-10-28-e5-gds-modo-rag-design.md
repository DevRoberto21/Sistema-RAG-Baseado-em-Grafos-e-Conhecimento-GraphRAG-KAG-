# E5.4 + E5.8 — GDS no contexto e modo `rag` — design

Data: 2026-10-28. Status: aprovado.

## Contexto

O pipeline do GraphRAG já responde ponta a ponta: `recuperar` → `montar_contexto` →
`gerar_resposta` → `responder` (E5.1–E5.3, E5.5–E5.7). Faltam duas tarefas para fechar o E5:

- **E5.4**: GDS. PageRank para ranquear o contexto, Louvain para comunidades e Shortest Path para
  ligar dois medicamentos.
- **E5.8**: modo `rag` (RAG tradicional) no `responder`, como em
  `2026-10-23-visao-graphrag-vs-rag-design.md`.

Sondagem de 2026-10-28 no grafo semente (GDS 2.13, 104 nós, 251 relações): projeção por Cypher,
`gds.pageRank.stream`, `gds.louvain.stream` e `gds.shortestPath.dijkstra.stream` rodam numa
transação só leitura (`routing_="r"`). Marevan → Advil sai
`marevan, varfarina, anticoagulante, ibuprofeno, advil`.

## Decisões

| Decisão | Escolha | Motivo |
|---|---|---|
| O que o GDS projeta | Só o subgrafo expandido da pergunta (até 60 nós), uma projeção por chamada | Sempre reflete o grafo atual, sem cache para invalidar depois da ingestão (M2). Projetar 60 nós é barato. |
| PageRank | Personalizado, com as seeds como `sourceNodes` | Ranqueia o que é central *para a pergunta*, não o hub global do grafo. |
| Uso do PageRank | Ordena os fatos do contexto | Troca o `shortcut` do E5.5 (`dist`/`confianca`). |
| Shortest Path | Dijkstra sem peso entre pares de seeds `Medicamento` | Mostra ao LLM a ligação entre os remédios da pergunta ("posso tomar X com Y?"). |
| Uso do caminho | Bloco próprio no contexto, antes dos fatos | O LLM vê a cadeia inteira de uma vez, sem montar o caminho a partir de fatos soltos. |
| Louvain | Só anota `comunidade` em cada nó do subgrafo | Serve para a cor na UI (E6.3) e para o artigo. Não muda o prompt. |
| Falha do GDS | O retrieval segue sem ranking; o erro fica em `r["gds"]["erro"]` | Mesmo padrão do `consultar` (E5.3): o GDS melhora o contexto, mas não pode derrubar a resposta. |
| Modo `rag` | Troca só o retrieval; `montar_contexto` e `gerar_resposta` são os mesmos | A spec de visão exige a mesma geração nos dois modos. Com subgrafo vazio, o montador já ordena os trechos por `score`. |
| Busca de chunks | `buscar_chunks` extraído de `buscar_seeds` e usado pelos dois modos | Os dois modos usam a mesma query, então a comparação do E7 é justa. |
| Confiança sem nós no contexto | Quando `contexto["nos"]` está vazio, a confiança conta só os chunks | No modo `rag`, ids de entidade que o LLM listar contariam como citação inválida e baixariam a confiança, o que enviesa o E7. |

## Módulos

| Arquivo | Épico | Mudança |
|---|---|---|
| `src/graphrag_bulas/gds.py` | E5.4 | novo: `ranquear(driver, r)` |
| `src/graphrag_bulas/retrieval.py` | E5.4, E5.8 | `buscar_chunks(driver, vetor, k)` extraído; `recuperar` chama `ranquear` |
| `src/graphrag_bulas/contexto.py` | E5.4 | ordena por `pagerank`; bloco de caminhos |
| `src/graphrag_bulas/rag_vetorial.py` | E5.8 | novo: `recuperar_vetorial(driver, pergunta, k=5)` |
| `src/graphrag_bulas/geracao.py` | E5.8 | confiança sem nós quando o contexto não tem nós |
| `src/graphrag_bulas/api.py` | E5.8 | `modo="rag"` chama `recuperar_vetorial` |

## E5.4 — `ranquear`

```python
def ranquear(driver, r) -> None
```

Recebe o dict de `expandir` e o altera no lugar:

- cada nó de `r["subgrafo"]["nos"]` ganha `pagerank: float | None` e `comunidade: int | None`;
- `r["gds"] = {"caminhos": [[id, ...], ...], "erro": str | None}`.

Passos, todos com `routing_="r"`:

1. Sem nós no subgrafo, devolve `caminhos = []` e não chama o GDS.
2. **Projeção** com nome único (`ctx_<uuid4 hex>`), por agregação Cypher:
   - nós: as `Entidade` cujo `id` está em `subgrafo.nos`;
   - relações: as de `RELACOES_DOMINIO` entre esses nós, não direcionadas;
   - nós isolados (uma seed sem aresta) entram com `OPTIONAL MATCH`.
3. **PageRank** (`gds.pageRank.stream`) com `sourceNodes` = os nós das seeds (`r["seeds"]`).
4. **Louvain** (`gds.louvain.stream`).
5. **Caminhos**: para cada par de seeds com label `Medicamento`, `gds.shortestPath.dijkstra.stream`
   sem peso. No máximo `MAX_MEDICAMENTOS = 3` seeds `Medicamento`, ou seja até 3 pares. Par sem
   caminho é omitido.
6. `finally`: `CALL gds.graph.drop($nome, false)`, que apaga a projeção mesmo com erro.

Erro do Neo4j/GDS (`neo4j.exceptions.Neo4jError`) em qualquer passo: `pagerank` e `comunidade`
ficam `None` em todos os nós, `caminhos = []` e `erro` recebe a mensagem. Não levanta.

O id não é único entre labels (o `shortcut` de `expandir`, ex.: `cefaleia`). A projeção herda
essa limitação.

`recuperar` passa a ser: `buscar_seeds` → `expandir` → `ranquear` → `consultar` (se houver `llm`).

## E5.4 — mudanças no `montar_contexto`

**Ordem dos fatos.** Chave, em ordem:

1. maior `pagerank` entre origem e destino, decrescente (`None` conta como 0);
2. `dist` mínima (como hoje);
3. `confianca` decrescente;
4. `origem`, `tipo`, `destino`.

Sem GDS (`pagerank` sempre `None`), a ordem é a mesma do E5.5. O comentário `shortcut:` sai.

**Bloco de caminhos.** Se `r.get("gds")` tem `caminhos`, o texto ganha, antes de "Fatos do
grafo:":

```
Caminhos entre medicamentos:
- Marevan -[CONTEM]-> Varfarina -[PERTENCE_A]-> Anticoagulante <-[INTERAGE_COM]- Ibuprofeno <-[CONTEM]- Advil
```

- Nomes vêm de `subgrafo.nos`. O tipo e a direção de cada passo vêm da aresta de
  `subgrafo.arestas` entre os dois nós (a primeira, na ordem da lista). Sem aresta, o passo sai
  `-[?]-`.
- Os ids dos nós dos caminhos entram em `ctx["nos"]`, para o LLM poder citá-los.
- O bloco não entra no corte de `max_fatos`.

## E5.8 — modo `rag`

`retrieval.py`:

```python
def buscar_chunks(driver, vetor, k) -> list[dict]  # {chunk_id, texto, fonte, score}
```

É a query de chunks que hoje está dentro de `buscar_seeds`, sem mudança. `buscar_seeds` passa a
chamá-la.

`rag_vetorial.py`:

```python
def recuperar_vetorial(driver, pergunta, k=5) -> dict
```

Devolve o mesmo formato de `recuperar`:

```python
{"seeds": [], "subgrafo": {"nos": [], "arestas": []},
 "trechos": buscar_chunks(driver, embed([pergunta])[0], k), "cypher": None}
```

Pergunta sem nenhum caractere de palavra (`\w`) devolve `trechos = []` sem chamar `embed`, como
`buscar_seeds`.

`api.py`: `modo="rag"` chama `recuperar_vetorial(driver, pergunta)` no lugar de `recuperar`. O
resto do fluxo não muda. No modo `rag`, o LLM é chamado uma vez (só a geração).

Resultado no contrato, como a spec de visão define: `subgrafo` vazio, `cypher = null`,
`nos = []` e `trechos` ordenados por `score` decrescente, cada um com `citado`.

`geracao.py`: se `contexto["nos"]` está vazio, `nos` sai `[]` e a confiança é
`PESO_SUPORTE[suporte] × chunks válidos / chunks citados`. Com nós no contexto, a fórmula é a
mesma do E5.6.

## Contrato

As chaves de `responder` não mudam. Mudanças aditivas:

- `subgrafo.nos[]` ganha `pagerank` e `comunidade` no modo `graphrag`.
- `modo="rag"` deixa de levantar `NotImplementedError`.

## Testes

| Arquivo | Neo4j | Casos |
|---|---|---|
| `tests/test_gds.py` | sim (`db`) | "Posso tomar Marevan com Advil?": a seed `marevan` está entre os 3 maiores `pagerank`; existe caminho de `marevan` a `advil`; todo nó tem `comunidade`; depois da chamada, `gds.graph.list()` não tem projeção `ctx_`; subgrafo vazio não chama o GDS; erro do GDS (forçado no teste, ex.: `monkeypatch` do nome para uma projeção que já existe) dá `erro` preenchido, `pagerank None` e não levanta |
| `tests/test_contexto.py` | não | `pagerank` maior vem primeiro mesmo com `dist` maior; sem `pagerank` a ordem do E5.5 se mantém; bloco de caminhos com nomes, tipos e direção; ids do caminho em `ctx["nos"]` |
| `tests/test_retrieval.py` | sim (`db`) | `recuperar` devolve `gds` e nós com `pagerank` |
| `tests/test_rag_vetorial.py` | sim (`db`) | trechos ordenados por `score`, no máximo `k`; subgrafo vazio e `cypher None`; pergunta sem palavra dá `trechos == []` |
| `tests/test_geracao.py` | não | contexto sem nós: nós citados pelo LLM não reduzem a confiança e `nos == []` |
| `tests/test_api.py` | sim (`db`) | `modo="rag"` devolve as mesmas chaves que `graphrag`, `subgrafo` vazio, `cypher None` e trechos por `score`; sai o teste `test_modo_rag_ainda_nao_existe` |

## Mudanças em outras specs

- `2026-10-28-e5-contexto-geracao-api-design.md`: a ordenação do E5.5 passa a usar o PageRank, e
  o contexto ganha o bloco de caminhos.
- `2026-10-23-visao-graphrag-vs-rag-design.md`: `subgrafo.nos[]` ganha `pagerank` e
  `comunidade`.

## Fora do escopo

- UI (E6), avaliação (E7), pipeline de ingestão (E2–E4).
- Expor `caminhos` ou `gds.erro` no contrato do `responder`.
- Pesos no Dijkstra (por `confianca` ou `gravidade`).
- Os minors do review final do E5.5–E5.7 (citação do Cypher sem trecho, `cypher` com erro no
  contrato, regra "entre colchetes").
