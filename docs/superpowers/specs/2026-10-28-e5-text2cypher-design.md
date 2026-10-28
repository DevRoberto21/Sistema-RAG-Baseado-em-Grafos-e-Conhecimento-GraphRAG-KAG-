# E5.3 — Text-to-Cypher — design

Data: 2026-10-28. Status: aprovado.

## Contexto

A spec `2026-10-28-e5-retrieval-seeds-expansao-design.md` dividiu o E5 em três partes e pôs o
E5.3 na parte 3. O E5.3 sai dessa parte e ganha spec própria, porque não depende da geração
(E5.6) e só usa o que já existe: `buscar_seeds` (E5.1), `expandir` (E5.2) e `get_llm()`.

Plano (`planejamento/PLANO_EQUIPE.md`): LLM gera Cypher com o schema no prompt, só leitura,
validado com `EXPLAIN`, com fallback para a expansão do E5.2.

## Decisões

| Decisão | Escolha | Motivo |
|---|---|---|
| Papel no pipeline | A expansão (E5.2) roda sempre. O Cypher gerado roda junto e o resultado entra no contexto como fatos diretos. | Se o Cypher falhar, só falta essa parte; a expansão ainda cobre a resposta. |
| Conteúdo do prompt | Schema escrito à mão + 4 exemplos neutros, com remédios fora do grafo | Melhora o Cypher sem vazar as perguntas-alvo nem o gold set do E7. |
| Referência às entidades | As seeds do E5.1 vão no prompt; o LLM filtra por `id` | Evita erro de acento, caixa, marca e genérico. |
| Implementação | Código próprio, sem dependência nova | `langchain-neo4j` e `neo4j-graphrag` trazem schema por APOC (com ruído de `Chunk`/`Bula`), formato próprio e geração de resposta, que é do E5.6. Ficam só nos créditos (E8.4). |

## Módulo

Arquivo novo: `src/graphrag_bulas/text2cypher.py`.

```python
class Consulta(BaseModel):
    cypher: str

class CypherInvalido(Exception): ...

gerar_cypher(llm, pergunta, seeds, anterior=None, erro=None) -> str
validar_cypher(driver, cypher) -> None          # levanta CypherInvalido
consultar(driver, llm, pergunta, seeds, tentativas=2) -> dict
```

- `gerar_cypher`: monta o prompt e chama `llm.with_structured_output(Consulta)`. Não acessa o
  Neo4j. `seeds` é a lista `entidades` de `buscar_seeds`.
- `validar_cypher`: as checagens da seção "Validação".
- `consultar`: gera, valida e executa. Nunca levanta exceção. Retorno:

```json
{"query": "MATCH ... LIMIT 50", "linhas": [{"medicamento": "Cozaar", "fonte_chunk_id": null}], "erro": null}
```

## Integração

Em `src/graphrag_bulas/retrieval.py`:

```python
def recuperar(driver, pergunta, llm=None):
    seeds = buscar_seeds(driver, pergunta)
    r = expandir(driver, seeds)
    r["cypher"] = consultar(driver, llm, pergunta, seeds["entidades"]) if llm else None
    return r
```

- `llm` é opcional. Sem ele, `recuperar` funciona como antes (mais a chave `cypher = None`).
- As `linhas` ficam separadas do `subgrafo`. O montador de contexto (E5.5) decide como usá-las.
  Converter linhas em nós e arestas fica fora do escopo.
- No contrato de `2026-10-23-visao-graphrag-vs-rag-design.md`, o campo `cypher` recebe
  `r["cypher"]["query"]`. Esse mapeamento é do E5.7.
- O E5.6 trata `erro == "sem_consulta"` como sinal de que o schema não responde à pergunta
  (apoio à recusa).

## Prompt

Constante no módulo, em pt-BR. LLM com `temperature=0`. Partes, nesta ordem:

1. **Regras.**
   - Gere uma única consulta Cypher de leitura.
   - Nunca use `CREATE`, `MERGE`, `SET`, `DELETE`, `CALL` ou `LOAD CSV`.
   - Use só os labels, relações e propriedades do schema.
   - Filtre entidades por `id`, usando só os ids da lista de seeds.
   - Leia `INTERAGE_COM` sem direção: `-[:INTERAGE_COM]-`.
   - Em interação com classe, desça por `PERTENCE_A` até os princípios ativos.
   - Ao retornar um fato de relação, retorne também `r.fonte_chunk_id`.
   - Retorne propriedades (`m.nome`), não nós inteiros.
   - Termine com `LIMIT 50`.
   - Se o schema não responde à pergunta, devolva `cypher` vazio.
2. **Schema.** Só a parte de domínio de `docs/modelagem.md` (seções 3 e 4): os 7 labels de
   entidade com `id`, `nome` e propriedades extras; as 7 relações com direção e propriedades; os
   vocabulários fechados de `frequencia` e `gravidade`; os 4 valores de `Populacao`. Não inclui
   `Bula`, `Secao`, `Chunk` nem embeddings. Um comentário no código manda manter o schema em
   sincronia com `docs/modelagem.md`.
3. **Exemplos (4).** Usam remédios fora do grafo semente, então nenhum id dos exemplos existe no
   banco:
   - "Quais efeitos raros a Novalgina pode causar?": `PODE_CAUSAR` com filtro em `frequencia`.
   - "Qual a dose de omeprazol no Losec?": propriedade `dose` de `CONTEM`.
   - "Algum remédio com dipirona é contraindicado para idosos?": `CONTEM` + `CONTRAINDICADO_EM`
     com `Populacao`.
   - "Qual a cor do comprimido de Losec?": `cypher` vazio.
4. **Seeds.** Uma linha por seed: `id (Label): nome`. Ex.: `marevan (Medicamento): Marevan`.
   Sem seeds, a linha diz "nenhuma".
5. **Pergunta.**
6. **Só na nova tentativa:** o Cypher anterior e a mensagem de erro.

Riscos aceitos:

- O LLM pode usar um id fora das seeds. A consulta volta sem linhas, sem erro, e a expansão
  cobre. O código não confere os ids.
- O 3º exemplo usa o mesmo padrão da pergunta-alvo "contraindicação por população". O padrão é
  geral do schema; a pergunta e os ids são outros.

## Validação

A pergunta vem do usuário. Prompt injection pode levar o LLM a gerar escrita ou chamada externa
(ex.: `apoc.load.json` com uma URL). As camadas abaixo não dependem de o LLM obedecer.

`validar_cypher(driver, cypher)` levanta `CypherInvalido(msg)` nesta ordem:

1. `cypher` vazio ou só espaços: mensagem `sem_consulta`.
2. Palavra proibida, por regex sem diferenciar caixa e com fronteira de palavra: `CALL`, `LOAD`,
   `CREATE`, `MERGE`, `SET`, `DELETE`, `DETACH`, `REMOVE`, `DROP`, `FOREACH`. `CALL` bloqueia
   APOC, GDS, `dbms.*` e subqueries.
3. `EXPLAIN <cypher>` falha (sintaxe, label inexistente etc.): a mensagem do Neo4j vira `msg`.
4. `summary.query_type != "r"`.

A regex roda antes do `EXPLAIN`, então texto proibido não chega ao Neo4j. Limite conhecido: a
regex também rejeita palavra proibida dentro de string literal (ex.: `'set'`). O efeito é
rejeição a mais, nunca escrita liberada.

Execução, só depois de validar:

- `session.execute_read`, em sessão com acesso de leitura. O servidor recusa escrita nesse modo.
- `neo4j.Query(cypher, timeout=TIMEOUT_S)`, com `TIMEOUT_S = 5`.
- `result.fetch(MAX_LINHAS)`, com `MAX_LINHAS = 50`, mesmo que a consulta não tenha `LIMIT`.
- Linhas via `record.data()`, sem as chaves `embedding` e `embedding_nome`, inclusive dentro de
  dicts e listas aninhados.

## Erros em `consultar`

`consultar` nunca levanta exceção. Em todo erro, `linhas = []` e a mensagem vai para
`logging.warning` (o E7 mede a taxa de falha).

| Falha | Nova tentativa? | Retorno |
|---|---|---|
| `cypher` vazio | não | `query=None`, `erro="sem_consulta"` |
| palavra proibida, `EXPLAIN` falha, tipo ≠ `r` | sim, até `tentativas` no total, com o erro no prompt | após a última: `query=<última>`, `erro=<msg>` |
| timeout ou erro na execução | não | `query=<cypher>`, `erro=<msg>` |
| LLM falha (rede, cota, saída inválida) | não | `query=None`, `erro=<msg>` |

## Testes

Arquivo novo: `tests/test_text2cypher.py`. LLM falso: classe com `with_structured_output()` que
devolve `Consulta`s de uma fila, em ordem, e guarda os prompts recebidos.

Sem Neo4j:

| Teste | Verifica |
|---|---|
| palavras proibidas | `CALL apoc.load.json(...)`, `create (n)`, `MERGE`, `LOAD CSV` rejeitados; `MATCH ... RETURN m.nome` passa; `'set'` em string é rejeitado (limite documentado) |
| prompt | contém `marevan (Medicamento): Marevan` e a pergunta; na nova tentativa, também o Cypher anterior e o erro |
| limpar embeddings | `embedding` e `embedding_nome` somem, inclusive em dict aninhado e em lista |

Com Neo4j (fixture `db`, pula sem Neo4j/semente):

| Teste | Verifica |
|---|---|
| validar ok | consulta de leitura sobre `cozaar` passa |
| sintaxe ruim | `MATCH (n RETURN n` levanta `CypherInvalido` com a mensagem do Neo4j |
| consultar feliz | Cypher de equivalência do Cozaar: `linhas` não vazio, `erro=None` |
| nova tentativa | 1ª resposta inválida, 2ª válida: `linhas` não vazio; o 2º prompt contém o erro |
| falha dupla | duas respostas inválidas: `linhas=[]`, `erro` preenchido, sem exceção |
| vazio | `cypher=""`: `query=None`, `erro="sem_consulta"`, LLM chamado 1 vez |
| escrita bloqueada | LLM devolve `CREATE (:X)`: contagem de nós igual antes e depois |
| LLM quebra | LLM levanta exceção: `erro` preenchido, sem exceção |
| `recuperar` | sem `llm`: `cypher is None`; com LLM falso: `r["cypher"]["linhas"]` não vazio |

LLM real (opcional): um teste de fumaça com o Gemini e "Posso tomar Marevan com Advil?". Espera
`erro=None` e alguma linha com `fonte_chunk_id`. Só roda com `GRAPHRAG_TESTAR_LLM=1`, porque é
não determinístico e gasta cota. Serve para conferir o prompt, não como gate.

Fora dos testes: timeout real (difícil provocar no semente) e a checagem de `query_type`
isolada (a regex barra antes; a checagem fica como defesa extra).

## Fora do escopo

- Usuário Neo4j só-leitura: RBAC é recurso Enterprise e o servidor é Community.
- Conferir se os ids da consulta estão nas seeds.
- Converter `linhas` em nós e arestas do subgrafo.
- Geração da resposta e recusa (E5.6), GDS e montador de contexto (E5.4/E5.5), API `responder`
  (E5.7/E5.8).
