# E5.5 + E5.6 + E5.7 — Contexto, geração e API — design

Data: 2026-10-28. Status: aprovado.

## Contexto

O retrieval já existe: `recuperar(driver, pergunta, llm=None)` devolve `seeds`, `subgrafo`
(`nos` com `dist`, `arestas` com `props`), `trechos` e `cypher` (E5.1, E5.2, E5.3).

Esta spec cobre a parte 3 do E5, menos o modo `rag`:

- **E5.5**: montador de contexto. Versão simples, sem GDS. O PageRank do E5.4 entra depois e
  só troca a ordenação.
- **E5.6**: geração da resposta com citação, recusa e score de confiança.
- **E5.7**: `responder(pergunta, modo)` com o contrato de
  `2026-10-23-visao-graphrag-vs-rag-design.md`.

Motivo da ordem: o caminho crítico do plano é E5.3 → E5.6 → E6.5 → E7.4. Fazer o E5.5 sem GDS
destrava a API para a UI e para a avaliação antes do E5.4.

## Decisões

| Decisão | Escolha | Motivo |
|---|---|---|
| Ordenação do contexto | `dist` e `confianca` das arestas, sem GDS | Destrava o E5.6. O E5.4 troca só a função de ordenação. |
| Chamadas ao LLM na geração | Uma, com structured output | Barato em cota e reproduzível no E7. Um verificador separado dobraria custo e latência; o E7 já mede fidelidade por fora. |
| Confiança | O LLM declara `suporte` e as citações; o código confere as citações e calcula o número | Auditável. LLM é mal calibrado para devolver um número direto. |
| Contexto vazio | Recusa sem chamar o LLM | Não gasta cota quando não há o que citar. |
| Falha do LLM na geração | Propaga a exceção | Sem LLM não há resposta. A spec de visão já prevê que a UI mostre o erro do modo. |
| Geração independente do grafo | `gerar_resposta` recebe só o contexto montado | O modo `rag` (E5.8) reusa a mesma geração, como a spec de visão exige. |

## Módulos

| Arquivo | Épico | Responsabilidade |
|---|---|---|
| `src/graphrag_bulas/contexto.py` | E5.5 | `montar_contexto(r, max_fatos=40, max_trechos=8)`. Função pura, sem Neo4j. |
| `src/graphrag_bulas/geracao.py` | E5.6 | `Resposta`, `RECUSA`, `gerar_resposta(llm, pergunta, contexto)`. Não acessa o Neo4j. |
| `src/graphrag_bulas/api.py` | E5.7 | `responder(pergunta, modo="graphrag", driver=None, llm=None)`. |

Fluxo: `recuperar` → `montar_contexto` → `gerar_resposta` → contrato.

## E5.5 — `montar_contexto`

Entrada: o retorno de `recuperar`. Saída:

```python
{
    "texto": str,            # vai para o prompt; "" quando não há nada
    "chunk_ids": set[str],   # chunks que podem ser citados
    "nos": set[str],         # ids de entidades que podem ser citadas
    "trechos": list[dict],   # trechos que entraram, no formato de r["trechos"]
    "sem_consulta": bool,    # r["cypher"]["erro"] == "sem_consulta"
}
```

### Texto

Três blocos, nesta ordem. Um bloco sem conteúdo não aparece.

```
Fatos do grafo:
- Marevan -[CONTEM {dose: 5 mg}]-> Varfarina [bula_marevan_composicao_0] (ids: marevan, varfarina)
- Varfarina -[INTERAGE_COM {gravidade: grave, efeito: ...}]-> AINEs [bula_marevan_interacoes_0] (ids: varfarina, aines)

Resultado da consulta Cypher:
- {"medicamento": "Advil", "fonte_chunk_id": "bula_advil_interacoes_1"}

Trechos de bula:
[bula_marevan_interacoes_0] (marevan) texto do chunk...
```

- **Fatos.** Uma linha por aresta:
  `nome da origem -[TIPO {props}]-> nome do destino [fonte] (ids: origem, destino)`.
  Os ids no fim deixam o LLM citar entidades em `nos`.
  O nome vem de `subgrafo.nos` pelo id; se o id não estiver lá, usa o próprio id. As props
  `fonte_chunk_id`, `confianca` e `metodo` não entram nas chaves; a fonte aparece como
  `[chunk_id]` no fim, e some se a aresta não tiver fonte. Sem outras props, sai `-[TIPO]->`.
  Os ids da origem e do destino entram em `nos`.
- **Ordem dos fatos.** Menor `dist` entre as duas pontas primeiro, depois maior `confianca`
  (ausente conta como 0), depois origem, tipo e destino. Corte em `max_fatos`. Comentário no
  código: `shortcut: ordena por dist/confianca; E5.4 troca por PageRank`.
- **Linhas do Cypher.** Só quando `r["cypher"]` existe e `erro is None`. Uma linha por registro,
  em JSON compacto (`ensure_ascii=False`, chaves ordenadas). O `fonte_chunk_id` de cada linha,
  quando houver, entra em `chunk_ids`.
- **Trechos.** Primeiro os trechos citados pelos fatos que entraram, na ordem dos fatos. Depois
  os demais trechos de `r["trechos"]`, por `score` decrescente (`None` por último), sem repetir
  `chunk_id`. Corte em `max_trechos`. Formato: `[chunk_id] (fonte) texto`, com o texto inteiro.
- **`chunk_ids`.** Os ids dos trechos que entraram, mais as fontes dos fatos e das linhas que
  entraram.
- **Vazio.** Sem fatos, sem linhas e sem trechos, `texto == ""`.

Os limites 40/8 deixam o prompt em uns 4–6 mil tokens. São parâmetros para o E7 ajustar.

## E5.6 — `gerar_resposta`

```python
class Resposta(BaseModel):
    resposta: str
    chunks: list[str]                          # chunk_ids que sustentam a resposta
    nos: list[str]                             # ids das entidades usadas
    suporte: Literal["total", "parcial", "nenhum"]

PESO_SUPORTE = {"total": 1.0, "parcial": 0.6, "nenhum": 0.0}
RECUSA = "Não encontrei nas bulas informação suficiente para responder com segurança."

gerar_resposta(llm, pergunta, contexto) -> dict
```

Retorno:

```python
{"resposta": str, "chunks": list[str], "nos": list[str], "confianca": float, "recusou": bool}
```

### Prompt

Constante no módulo, em pt-BR. Quem chama passa o LLM com `temperature=0`. Partes:

1. Regras:
   - Responda em português, só com o contexto abaixo, sem conhecimento próprio.
   - Em `chunks`, liste os chunk_ids (entre colchetes no contexto) que sustentam a resposta. Em
     `nos`, os ids das entidades usadas.
   - `suporte`: `total` se o contexto sustenta toda a resposta, `parcial` se sustenta só parte,
     `nenhum` se não sustenta.
   - Em pergunta sobre interação, contraindicação ou dose, oriente procurar médico ou
     farmacêutico.
2. Só quando `sem_consulta`: "A consulta estruturada indicou que o schema do grafo não cobre esta
   pergunta."
3. O `texto` do contexto.
4. A pergunta.

### Depois da chamada

1. **Contexto vazio:** devolve a recusa sem chamar o LLM.
2. **Filtro de citações:** mantém só os `chunks` que estão em `contexto["chunk_ids"]` e os `nos`
   que estão em `contexto["nos"]`. Sem repetidos, na ordem do LLM.
3. **Confiança:** `PESO_SUPORTE[suporte] × válidas / citadas`, somando chunks e nós, arredondada
   a 2 casas. Sem nenhuma citação, a razão é 0.
4. **Recusa** quando `suporte == "nenhum"` ou quando não sobra nenhum chunk válido. Na recusa:
   `resposta = RECUSA`, `chunks = []`, `nos = []`, `confianca = 0.0`, `recusou = True`.

Uma falha do LLM (rede, cota, saída inválida) propaga a exceção.

## E5.7 — `responder`

```python
def responder(pergunta, modo="graphrag", driver=None, llm=None) -> dict
```

- `modo="rag"`: levanta `NotImplementedError("modo rag: E5.8")`.
- Outro modo: levanta `ValueError`.
- `llm=None`: usa `get_llm(temperature=0)`.
- `driver=None`: abre com `get_driver()` e fecha no fim da chamada. Quem chama muitas vezes (UI,
  E7) passa o próprio driver.
- O mesmo `llm` serve ao Text-to-Cypher (`recuperar(..., llm=llm)`) e à geração.

Contrato (spec de visão, com dois campos aditivos: `recusou` e `trechos[].citado`):

```json
{
  "modo": "graphrag",
  "resposta": "...",
  "subgrafo": {"nos": [], "arestas": []},
  "cypher": "MATCH ...",
  "nos": ["varfarina", "ibuprofeno"],
  "confianca": 0.86,
  "recusou": false,
  "trechos": [
    {"chunk_id": "...", "texto": "...", "fonte": "marevan", "score": null, "citado": true}
  ]
}
```

- `subgrafo`: a expansão completa do `recuperar`, para a UI desenhar.
- `cypher`: `r["cypher"]["query"]`, ou `null` (sem LLM no Cypher, sem consulta ou falha do LLM).
- `nos`: as entidades citadas e validadas.
- `trechos`: os trechos que entraram no contexto, cada um com `citado` (está em `chunks`).

## Testes

LLM falso no padrão do E5.3, com uma fila de respostas por schema (`Consulta` para o
Text-to-Cypher, `Resposta` para a geração), guardando os prompts.

| Arquivo | Neo4j | Casos |
|---|---|---|
| `tests/test_contexto.py` | não; `r` montado à mão | ordem dos fatos por `dist` e `confianca`; corte em `max_fatos` e `max_trechos`; trechos citados pelos fatos vêm primeiro; `fonte_chunk_id`/`confianca`/`metodo` fora do texto; linhas do Cypher só com `erro is None`; `sem_consulta`; contexto vazio dá `texto == ""` |
| `tests/test_geracao.py` | não | resposta feliz com confiança 1.0; citação inventada descartada e confiança reduzida; `suporte="nenhum"` recusa; nenhum chunk válido recusa; contexto vazio recusa sem chamar o LLM; nota de `sem_consulta` no prompt; exceção do LLM propaga |
| `tests/test_api.py` | sim (fixture `db`) | contrato com todas as chaves; `trechos[].citado`; `modo="rag"` levanta `NotImplementedError`; modo inválido levanta `ValueError` |
| `tests/test_api.py` | Gemini real, opcional (`GRAPHRAG_TESTAR_LLM=1`) | "Posso tomar Marevan com Advil?" não recusa e cita chunk; "Qual a cor do comprimido de Cozaar?" recusa |

O teste com o Gemini real confere o prompt; não é gate.

## Mudanças em outras specs

- `2026-10-23-visao-graphrag-vs-rag-design.md`: o contrato ganha `recusou` e `trechos[].citado`.
  No modo `rag`, todos os trechos do top-k entram no contexto.

## Fora do escopo

- GDS e PageRank (E5.4). A ordenação do E5.5 é trocada quando ele existir.
- Modo `rag` (E5.8).
- Streaming da resposta, cache de driver, histórico de conversa.
