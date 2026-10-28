# E5 parte 1 — Seeds híbridas e expansão multi-hop (E5.1 + E5.2) — design

Data: 2026-10-28. Status: aprovado (decisão de seeds: híbrido vetor + fulltext).

## Contexto

O E5 foi dividido em três partes, cada uma com spec e plano próprios:

1. **Retrieval (este documento):** E5.1 seeds + E5.2 expansão multi-hop. Sem LLM.
2. GDS + montador de contexto: E5.4 + E5.5.
3. Geração + API: E5.3 + E5.6 + E5.7 + E5.8 (`responder(pergunta, modo)`).

A parte 1 transforma uma pergunta em um subgrafo com trechos de bula. As partes 2 e 3 consomem
esse subgrafo. Tudo roda sobre o grafo semente (E1.4) e os embeddings bge-m3 já gravados.

## Evidência que guiou o design

Sondagem em 2026-10-28 com as perguntas-alvo de `docs/modelagem.md`, seção 1:

| Pergunta | Vetor (`entidade_embedding`), top-5 | Fulltext (`entidade_nomes`) |
|---|---|---|
| Posso tomar Marevan com Advil? | marevan 0.83, advil 0.82, enalapril 0.70, anti_hipertensivo 0.70 | marevan, advil |
| Varfarina interage com algum AINE? | varfarina 0.81, aspirina 0.71, enalapril 0.71, bra 0.70 | varfarina 3.6, aine 0.78 |
| Quais anti-hipertensivos são contraindicados na gravidez? | anti_hipertensivo 0.80, hipertensao 0.77, ..., gestante 0.72 | anti_hipertensivo 3.9, aine 1.9, gestante 1.4 |
| Que efeitos losartana e enalapril têm em comum? | enalapril 0.83, losartana 0.81, alopecia 0.70 | losartana 3.6, enalapril 3.4 |
| Qual a dose de Cozaar para cães? | cozaar 0.79, enalapril 0.69 | cozaar 1.9, farmoquimica 1.2, ... |

2ª sondagem, fulltext só com palavras de 4+ letras: Marevan/Advil → marevan, advil; AINE →
varfarina, aine; gravidez → anti_hipertensivo, aine, gestante; efeitos → losartana, enalapril;
cães → cozaar; hipertensão → hipertensao; mesmo princípio ativo → cozaar.

Conclusões:

- No vetor, acertos ficam em ~0.79–0.83 e o ruído em ~0.66–0.73. O vetor perde entidades com
  score baixo (`aine`, `gestante`).
- O fulltext acha nomes próprios e `aine`, mas também traz ruído de palavras comuns.
- Nenhum dos dois sozinho basta. A união (vetor com corte 0.75, fulltext com palavras de 4+
  letras) cobre as perguntas-alvo.
- Subgrafo de 2 saltos sobre o semente: 22–51 nós por pergunta, abaixo de `max_nos` = 60.

## Módulo

Arquivo novo: `src/graphrag_bulas/retrieval.py`. Reutiliza `embed()` e `get_driver()`.

```python
buscar_seeds(driver, pergunta, k_chunks=5) -> dict
expandir(driver, seeds, saltos=2, max_nos=60) -> dict
recuperar(driver, pergunta) -> dict   # buscar_seeds + expandir
```

Todas as funções só leem o grafo (`execute_query` com `routing_="r"`).

## E5.1 — `buscar_seeds`

1. Embedding da pergunta com `embed([pergunta])[0]`. Sem prefixo de query (bge-m3 não usa).
2. **Entidades por vetor:** `db.index.vector.queryNodes('entidade_embedding', 10, $v)`. Fica com
   `score >= MIN_SCORE_VETOR` (0.75).
3. **Entidades por fulltext:** `db.index.fulltext.queryNodes('entidade_nomes', $termos)`, top 10,
   sem corte de score. `$termos` = palavras da pergunta (`\w+`) com **4 letras ou mais**, cada
   uma unida por espaço (OR). Sem escape: `\w+` já descarta os caracteres especiais do Lucene
   e o filtro de tamanho descarta `AND`/`OR`/`NOT`. O índice usa `standard-no-stop-words`: sem
   o filtro, "a" casa com "Farmoquímica S/A" e "de" com "dor de cabeça". Com o filtro, a 2ª
   sondagem (abaixo) só traz acertos, mais `aine` em "anti-hipertensivos" (ruído tolerável). Um
   corte relativo de score perderia `aine` em "Varfarina interage com algum AINE?" (0.78 contra
   3.6 da varfarina), por isso não há corte.
4. **União das entidades** por `id`. Cada seed guarda `fontes` (`["vetor"]`, `["fulltext"]` ou as
   duas) e os dois scores (ou `None`). Ordem: seeds nas duas fontes primeiro, depois maior score
   vetorial.
5. **Chunks por vetor:** `db.index.vector.queryNodes('chunk_embedding', k_chunks, $v)`, sem corte,
   com `fonte` = `id` da `Bula` dona do chunk.
   Os chunks servem de texto de apoio; o corte nas entidades é o que controla o subgrafo.

Retorno:

```json
{
  "entidades": [{"id": "marevan", "nome": "Marevan", "labels": ["Medicamento"],
                 "fontes": ["vetor", "fulltext"], "score_vetor": 0.83, "score_fulltext": 1.94}],
  "chunks": [{"chunk_id": "bula_marevan_indicacoes_0", "texto": "...", "fonte": "bula_marevan", "score": 0.79}]
}
```

`labels` não inclui `Entidade`. `MIN_SCORE_VETOR`, `MIN_LETRAS_TERMO` e os top-k ficam como
constantes no topo do módulo, com as sondagens como justificativa. Recalibrar quando o corpus
inteiro (M2) estiver no grafo.

`id` é único por label, não em `:Entidade` (ex.: `cefaleia` existe como `Condicao` e como
`EfeitoAdverso`). A seed é chave por `id`; `expandir` parte de todos os nós com aquele `id`, e
os nós do subgrafo são chave por `(id, label)`.

Pergunta vazia ou só com pontuação: retorna listas vazias, sem chamar o Neo4j.

## E5.2 — `expandir`

Parte das entidades-seed e percorre só **relações de domínio**, sem direção:
`CONTEM`, `PERTENCE_A`, `INTERAGE_COM`, `INDICADO_PARA`, `CONTRAINDICADO_EM`, `PODE_CAUSAR`,
`FABRICADO_POR`. Não percorre `MENCIONA`, `DESCREVE`, `TEM_SECAO`, `TEM_CHUNK` (documento não é
fato).

Por que 2 saltos a partir de **cada** seed bastam: as perguntas-alvo têm caminhos de até 4
saltos, mas ligam duas seeds. Ex.: Marevan–Advil: `marevan→varfarina→aine` (`bula_marevan_interacoes_0`) e
`advil→ibuprofeno→anticoagulante` (`bula_advil_interacoes_1`); cada aresta fica a 2 saltos de uma
seed, e a união das vizinhanças traz as duas.

Cypher (esqueleto):

```cypher
MATCH (s:Entidade) WHERE s.id IN $ids
MATCH p = (s)-[:CONTEM|PERTENCE_A|INTERAGE_COM|INDICADO_PARA|CONTRAINDICADO_EM|PODE_CAUSAR|FABRICADO_POR*1..2]-(n:Entidade)
WITH n, min(length(p)) AS dist, collect(p) AS ps
ORDER BY dist, n.id
LIMIT $max_nos
...
```

Corte por `max_nos` (60): fica com os nós mais próximos das seeds (`dist`, depois `id` para ser
determinístico). Seeds entram sempre. As arestas retornadas são só as que ligam dois nós
mantidos.

**Trechos:** a união de

- chunks-seed de `buscar_seeds` (com `score`), e
- chunks citados em `fonte_chunk_id` das arestas mantidas (`score = None`), com o texto lido do
  nó `Chunk`.

Sem duplicatas por `chunk_id`. Ordem: primeiro os citados por aresta, depois os chunks-seed por
score.

Retorno (mesmo formato de `subgrafo` e `trechos` do contrato de
`2026-10-23-visao-graphrag-vs-rag-design.md`):

```json
{
  "seeds": ["marevan", "advil"],
  "subgrafo": {
    "nos": [{"id": "varfarina", "nome": "Varfarina", "labels": ["PrincipioAtivo"], "dist": 1}],
    "arestas": [{"origem": "varfarina", "destino": "aine", "tipo": "INTERAGE_COM",
                 "props": {"gravidade": "desconhecida", "fonte_chunk_id": "bula_marevan_interacoes_0",
                           "confianca": 1.0, "metodo": "manual"}}]
  },
  "trechos": [{"chunk_id": "bula_marevan_interacoes_0", "texto": "...", "fonte": "bula_marevan", "score": null}]
}
```

`origem`/`destino` seguem a direção gravada no grafo. `fonte` = `id` da `Bula` dona do chunk.

Sem seeds: retorna subgrafo vazio e só os chunks-seed (se houver).

## `recuperar`

`expandir(driver, buscar_seeds(driver, pergunta))`. É o ponto de entrada que a parte 2 usa.

## Testes

Arquivo novo: `tests/test_retrieval.py`. Usa a fixture `db` (pula sem Neo4j/semente).

| Teste | Verifica |
|---|---|
| seeds Marevan/Advil | `{"marevan", "advil"} ⊆ seeds` |
| seeds AINE | `{"varfarina", "aine"} ⊆ seeds` (`aine` só vem do fulltext) |
| seeds gravidez | `{"anti_hipertensivo", "gestante"} ⊆ seeds` |
| ruído vetorial | `enalapril` não é seed de "Posso tomar Marevan com Advil?" |
| caminho Marevan–Advil | subgrafo tem a aresta `INTERAGE_COM` e os trechos incluem `bula_marevan_interacoes_0` e `bula_advil_interacoes_1` |
| gravidez | subgrafo tem `cozaar -CONTRAINDICADO_EM-> gestante` |
| efeitos comuns | subgrafo tem ao menos um `EfeitoAdverso` ligado a `cozaar` e a `renitec` |
| `max_nos` | `len(nos) <= max_nos` e seeds sempre presentes |
| só leitura | contagem de nós e relações igual antes e depois de `recuperar` |
| pergunta vazia | `buscar_seeds(db, "?")` devolve listas vazias |
| caracteres especiais | pergunta com `"`, `(`, `:`, `/`, `~`, `*`, `[` não levanta erro e acha as seeds |

Teste sem Neo4j: `termos_fulltext` (unitário puro).

## Fora do escopo

- Text-to-Cypher (E5.3), GDS e ranqueamento (E5.4/E5.5), LLM e geração (E5.6), API `responder`
  (E5.7/E5.8). Ficam para as partes 2 e 3.
- Fulltext em `chunk_texto` para os chunks-seed. Os chunks vêm só do vetor; o fulltext entra nas
  entidades, onde a sondagem mostrou o ganho.
- Recalibrar limiares no corpus inteiro. Fica para depois do M2.
- Fusão por RRF. Com as duas regras simples a sondagem já fecha as perguntas-alvo; RRF pode entrar
  se o corpus inteiro mostrar ruído.
