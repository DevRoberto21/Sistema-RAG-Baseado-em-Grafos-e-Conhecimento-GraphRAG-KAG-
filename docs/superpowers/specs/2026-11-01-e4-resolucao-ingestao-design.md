# E4 — Resolução de entidades e ingestão no Neo4j — design

Data: 2026-11-01. Status: aprovado.

## Contexto

A extração do corpus (E3.4) terminou para as 25 bulas do escopo (`logs/bulas_escopo.txt`):
`data/processed/extracoes.jsonl` tem 561 chunks, 3185 relações e 639 descartes. Os 8 chunks em
que o LLM devolveu JSON quebrado ficam fora (1,4% do corpus); o texto deles entra no grafo, só
sem relações.

A saída tem muitas duplicatas, porque cada chunk foi extraído isolado. Ids únicos por label:

| Label | Ids únicos | Exemplos de duplicata |
|---|---|---|
| ClasseTerapeutica | 101 | `aines`, `anti_inflamatorios_nao_esteroides`, `antiinflamatorios_nao_esteroides`; `inhibidores_da_eca`, `inibidor_da_eca`; `beta_blockers`, `betabloqueadores` |
| PrincipioAtivo | 200 | `litio`, `lito`, `carbonato_de_litio`; nomes comerciais como `cipro`, `aspirina` |
| Condicao | 527 | — |
| EfeitoAdverso | 853 | — |

O grafo semente (E1.4, `cypher/seed.cypher`) tem 5 dessas bulas inseridas à mão, com ids
canônicos (`aine`, `ieca`, `bra`, `anticoagulante`...) e sinônimos.

## Decisões

| Decisão | Escolha | Motivo |
|---|---|---|
| Seed e LLM | Os dois no mesmo grafo. O seed roda primeiro e define os ids canônicos; o LLM soma por cima | Relação que o seed já tem fica `metodo='manual'`, `confianca=1.0`; o LLM não sobrescreve. |
| Resolução | Regras + dicionário curado + similaridade de embedding (bge-m3) com limiar | É o que o PLANO_EQUIPE pede no E4.2. Determinístico e barato. Juiz por LLM fica fora. |
| Arquitetura | Duas etapas com arquivo intermediário: `resolucao.py` grava `grafo.jsonl`; `ingestao.py` carrega no Neo4j | Resolução testável sem Neo4j; o arquivo é inspecionável; o relatório (E4.5) sai do mapeamento. |
| Chunks no Neo4j | Só os das 25 bulas do escopo (569) | Grafo e RAG vetorial usam o mesmo corpus, então a comparação do E7 é justa. |
| Texto dos chunks do seed | Substituído pelo texto real do corpus quando o id coincide | O RAG vetorial usa o corpus real. O relatório lista os chunks do seed alterados. |
| Confiança baixa | Toda relação entra, com `confianca` | Quem filtra é o retrieval (E5). |
| Relação repetida | Uma linha por `(rel, origem, destino)`; propriedades e `fonte_chunk_id` do chunk de maior `confianca` | `fonte_chunk_id` é uma string só (`docs/modelagem.md`). Os outros chunks aparecem em `MENCIONA`. |
| Mapeamento antigo | `ingestao --recriar` apaga o banco e roda tudo de novo | `MERGE` sozinho não remove nós de um mapeamento antigo. |

## Módulos

### `src/graphrag_bulas/resolucao.py` (E4.1, E4.2)

Lê `extracoes.jsonl` e grava `data/processed/grafo.jsonl` e `logs/pares_candidatos.csv`.

**Passo 1 — normalização por regra.** `normalizar(id, label) -> str`:

- Todos os labels: correções de grafia vistas nos dados (`inhibidor` → `inibidor`).
- `PrincipioAtivo`: tira o sal (`_potassica`, `_sodica`, `_medoxomila`, `cloridrato_de_`,
  `maleato_de_`, `carbonato_de_`...), como manda `docs/modelagem.md`.
- `ClasseTerapeutica`: singular palavra por palavra (`aines` → `aine`, `betabloqueadores` →
  `betabloqueador`). Só neste label: em `Condicao` a regra quebraria `diabetes`.

**Passo 2 — dicionário curado.** `data/curadoria/sinonimos.json`, por label:
`{label: {id_canonico: [variantes]}}`. As variantes passam por `slug` e `normalizar` antes da
consulta. Começa com:

- ids e sinônimos do seed (`aine`, `ieca`, `bra`, `anticoagulante`, `salicilato`...);
- nome comercial usado como princípio ativo → princípio ativo, gerado de
  `extracao.COMPOSICAO` (`cipro` → `ciprofloxacino`, `aspirina` → `acido_acetilsalicilico`).

Cresce a cada rodada, olhando o relatório.

**Passo 3 — similaridade de embedding.** O que não saiu do dicionário tem o `nome` comparado por
embedding (bge-m3, `embeddings.embed`) contra os canônicos e os outros ids, só dentro do mesmo
label. Cosseno ≥ limiar funde no id canônico, ou no id mais frequente se nenhum for canônico.

- Bloqueio: nunca funde dois nomes que diferem por prefixo de sentido oposto (`hiper`/`hipo`,
  `bradi`/`taqui`, `hipertensao`/`hipotensao`). O embedding acha esses pares quase iguais.
- Limiar: o script grava em `logs/pares_candidatos.csv` os pares com cosseno entre 0,80 e 0,95
  (colunas `label, id_a, id_b, cosseno, mesmo`). Alguém da equipe marca `mesmo` = `s`/`n` em
  cerca de 100 pares e salva em `data/curadoria/pares_rotulados.csv`. Com esse arquivo, o
  script escolhe o menor limiar com precisão ≥ 0,95. Sem ele, usa 0,92 e avisa no log e no
  relatório.

**Saída.** Mapa `(label, id_original) -> id_canonico`. Cada nó fica com:

- `nome`: o do seed se for canônico do seed, senão a forma mais frequente;
- `sinonimos`: as outras formas de `nome` vistas.

O mesmo id em dois labels (`hemorragia` como `Condicao` e `EfeitoAdverso`) fica como dois nós,
como no seed.

### `data/processed/grafo.jsonl`

Uma linha por item:

- nó: `{"tipo": "no", "label", "id", "nome", "sinonimos"}`
- relação: `{"tipo": "rel", "rel", "origem", "destino", "frequencia", "gravidade", "efeito",
  "dose", "confianca", "fonte_chunk_id", "chunks"}`. `chunks` é a lista de todos os chunks que
  sustentam a relação.

Relação cuja ponta some depois do mapeamento é descartada e contada no relatório.

### `src/graphrag_bulas/ingestao.py` (E4.3, E4.4)

Carga idempotente: só `UNWIND` + `MERGE`, em lotes de 500. Ordem:

1. `cypher/schema.cypher` e `cypher/seed.cypher` (idempotentes).
2. Documentos das 25 bulas, de `chunks.jsonl` e `data/raw/manifesto.jsonl`: `Bula`
   (`arquivo`, `data_publicacao`, `tipo`), `Secao`, `Chunk` (`SET texto`), `DESCREVE`,
   `TEM_SECAO`, `TEM_CHUNK`; `Medicamento.registro_anvisa`; `Fabricante` + `FABRICADO_POR`
   (`fonte_chunk_id` nulo).
3. `CONTEM` de `extracao.COMPOSICAO`, `fonte_chunk_id` nulo, `metodo='manual'`. O `MERGE` não
   apaga a `dose` que o seed já tem.
4. Nós de entidade: `MERGE` por id com o label e `:Entidade`; `ON CREATE SET nome`; `sinonimos`
   viram a união dos atuais com os novos.
5. Relações de domínio: `MERGE` + `ON CREATE SET metodo='llm', confianca, fonte_chunk_id` e
   propriedades. Relação do seed fica como está.
6. `MENCIONA`: cada chunk de `chunks` aponta para as duas pontas da relação.
7. `embeddings.embed_missing` (já existe): só grava o que falta.

`--recriar` roda `MATCH (n) DETACH DELETE n` antes do passo 1.

### Relatório (E4.5)

`logs/relatorio_e4.md`. `resolucao` reescreve o arquivo com os cinco primeiros itens;
`ingestao` acrescenta os dois últimos:

- nós por label antes e depois da resolução, e quantos cada passo fundiu (regra, dicionário,
  embedding) — métrica do artigo;
- relações por tipo antes e depois de juntar as repetidas;
- relações descartadas por ponta ausente;
- as 30 maiores fusões por embedding, com o cosseno, para conferir a olho;
- ids que aparecem uma vez só e não se fundiram (candidatos ao dicionário);
- chunks do seed cujo texto mudou;
- contagens no Neo4j depois da carga contra as de `grafo.jsonl`.

## Erros

| Caso | Comportamento |
|---|---|
| Relação com ponta ausente depois do mapeamento | Descartada e contada; a carga segue. |
| Neo4j fora do ar | Para com mensagem clara. Rodar de novo é seguro (só `MERGE`). |
| Sem `pares_rotulados.csv` | Limiar 0,92, aviso no log e no relatório. |

## Testes

- `tests/test_resolucao.py`, sem Neo4j e sem modelo: normalização (sal, plural de classe,
  grafia), consulta ao dicionário, bloqueio `hiper`/`hipo`, escolha do canônico, junção de
  repetidas pela maior `confianca`, escolha do limiar a partir de pares rotulados. O embedding
  é trocado por vetores fixos.
- `tests/test_ingestao.py`: montagem dos lotes direto; carga no Neo4j real com o mesmo skip dos
  testes atuais. Verifica que rodar duas vezes não duplica nada e que uma relação do seed
  continua `metodo='manual'`.

## Uso

```
uv run python -m graphrag_bulas.resolucao                # extracoes.jsonl -> grafo.jsonl + pares_candidatos.csv
uv run python -m graphrag_bulas.ingestao [--recriar]     # grafo.jsonl -> Neo4j + relatorio_e4.md
```

## Fora de escopo

- Os 8 chunks sem extração.
- Juiz por LLM para pares na zona cinzenta.
- Mudanças no retrieval (E5).
- Embedding de relações.
