# Gold set de extração (E2.5)

Anotação manual de entidades e relações de 5 bulas: Cozaar, Marevan, Advil, Renitec e Aspirina.
Serve de referência para medir a extração por LLM (E3). O schema está em
[`docs/modelagem.md`](../../docs/modelagem.md).

## Fluxo

1. Abra `bula_<med>.json` e preencha `anotador` com o seu nome.
2. Para cada chunk, leia `texto` e preencha `entidades` e `relacoes`. **Não altere `id`, `tipo` nem
   `texto`.**
3. Rode `uv run python -m graphrag_bulas.gold validar` até chegar a 0 erros.
4. Faça o commit do JSON.

`uv run python -m graphrag_bulas.gold preparar` recria apenas os arquivos que não existem. Ele nunca
sobrescreve uma anotação.

## Formato

```json
{
  "id": "bula_cozaar_reacoes_adversas_0",
  "tipo": "reacoes_adversas",
  "texto": "... Tontura: comum. ... Cefaleia: incomum ...",
  "entidades": [
    {"id": "cozaar", "label": "Medicamento", "nome": "Cozaar"},
    {"id": "tontura", "label": "EfeitoAdverso", "nome": "Tontura"},
    {"id": "cefaleia", "label": "EfeitoAdverso", "nome": "Cefaleia"}
  ],
  "relacoes": [
    {"tipo": "PODE_CAUSAR", "origem": "cozaar", "destino": "tontura", "props": {"frequencia": "comum"}},
    {"tipo": "PODE_CAUSAR", "origem": "cozaar", "destino": "cefaleia", "props": {"frequencia": "incomum"}}
  ]
}
```

Exemplo de interação, no chunk de interações do Cozaar:

```json
{"tipo": "INTERAGE_COM", "origem": "losartana", "destino": "aine",
 "props": {"gravidade": "moderada", "efeito": "redução do efeito anti-hipertensivo"}}
```

## Regras

- **Só o que o chunk afirma.** Não use conhecimento externo. Se o fato está em outro chunk, anote-o lá.
- **`entidades`** lista tudo que é ponta de alguma relação do chunk, inclusive o medicamento, que já
  vem preenchido. Se o medicamento não aparecer em nenhuma relação do chunk, remova-o.
- **IDs** são slugs minúsculos, sem acento, com `_` no lugar de espaço (`insuficiencia_renal`).
  Reaproveite os IDs do grafo semente (`cypher/seed.cypher`) quando a entidade já existir lá.
  Princípio ativo usa o nome da DCB sem sal (`losartana`, não `losartana potássica`).
- **Labels:** `Medicamento`, `PrincipioAtivo`, `ClasseTerapeutica`, `Condicao`, `EfeitoAdverso`,
  `Fabricante`, `Populacao`. `Populacao` só aceita `gestante`, `lactante`, `pediatrico` e `idoso`.
- **Relações e pontas aceitas:**

| Relação | Origem | Destino | `props` |
|---|---|---|---|
| `INDICADO_PARA` | Medicamento | Condicao | — |
| `CONTRAINDICADO_EM` | Medicamento | Condicao, Populacao | — |
| `PODE_CAUSAR` | Medicamento | EfeitoAdverso | `frequencia` |
| `INTERAGE_COM` | PrincipioAtivo | PrincipioAtivo, ClasseTerapeutica | `gravidade`, `efeito` |
| `PERTENCE_A` | PrincipioAtivo | ClasseTerapeutica | — |
| `CONTEM` | Medicamento | PrincipioAtivo | `dose` |
| `FABRICADO_POR` | Medicamento | Fabricante | — |

- **`frequencia`:** `muito_comum`, `comum`, `incomum`, `rara`, `muito_rara` ou `desconhecida`.
  Quando a bula dá uma faixa ("incomum a comum"), use a mais frequente.
- **`gravidade`:** `grave`, `moderada`, `leve` ou `desconhecida`. Use `desconhecida` quando o texto
  não deixar claro. Não infira a gravidade.
- **`efeito`:** texto curto, com as palavras da bula.
- Chunk sem nenhum fato do schema fica com `"relacoes": []`.
