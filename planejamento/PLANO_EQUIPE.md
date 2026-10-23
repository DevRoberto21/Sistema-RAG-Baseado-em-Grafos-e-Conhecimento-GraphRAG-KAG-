# Plano da Equipe — GraphRAG/KAG sobre Bulas de Medicamentos

Prazo: **25 dias** (D1 = início, D25 = entrega e defesa). Equipe: **6 pessoas**.
Fonte dos requisitos: `planejamento/Projeto Final_ GraphRAG e KAG em Ciência da Computação (1).pdf`.

> Atenção: a especificação diz "equipes de 2 a 5 alunos". Confirmar com o professor que 6 é aceito.

## Papéis

| Pessoa | Papel | Dono dos épicos |
|---|---|---|
| P1 | Tech lead + modelagem Neo4j | E0, E1 |
| P2 | Dados (corpus de bulas) → depois avaliação | E2, E7 |
| P3 | Extração NER/RE com LLM | E3 |
| P4 | Resolução de entidades + ingestão + embeddings | E4 |
| P5 | Retrieval híbrido + algoritmos de grafo + GraphRAG | E5 |
| P6 | Interface + visualização + proveniência | E6 |
| Todos | Artigo, README, defesa (cada um escreve a seção da sua parte) | E8 |

## Marcos

| Marco | Dia | Critério de pronto | Fase da spec |
|---|---|---|---|
| M1 | D5 | Schema no Neo4j (constraints + índices) e **grafo semente** com 5 bulas inseridas à mão | Fase 1 |
| M2 | D12 | Pipeline completo: bulas → NER/RE → resolução → Neo4j, corpus inteiro ingerido | Fase 2 |
| M3 | D18 | Pergunta → retrieval híbrido multi-hop → resposta com citações, ponta a ponta | Fase 3 |
| M4 | D21 | Feature freeze: UI integrada, avaliação rodada | — |
| M5 | D25 | Repo final, artigo SBC, slides, defesa | Fase 4 |

O grafo semente (M1) existe para que P5 e P6 comecem cedo, sem esperar a ingestão real (M2).

## Caminho crítico

```
E0.1 → E1.2 → E1.3 → E3.2 → E3.4 → E4.4 → E5.3 → E5.6 → E6.5 → E7.4 → E8.3
```

Atraso em qualquer tarefa dessa cadeia atrasa a entrega. As outras tarefas têm folga.

---

## E0 — Setup e infraestrutura (P1) — D1–D3

| ID | Tarefa | Resp. | Depende de | Dias |
|---|---|---|---|---|
| E0.1 | Estrutura do repo (`src/`, `data/`, `tests/`, `docs/`), `pyproject`/`requirements` | P1 | — | D1 |
| E0.2 | `docker-compose` com Neo4j 5 + plugins APOC e GDS | P1 | E0.1 | D1–D2 |
| E0.3 | Escolher provedor de LLM e modelo de embedding; `.env.example`; testar cota/custo | P1, P3 | — | D1–D2 |
| E0.4 | CI simples (lint + pytest) e convenção de branches/PR | P1 | E0.1 | D2–D3 |

## E1 — Domínio e modelagem LPG (P1) — D1–D5 — entrega Fase 1

| ID | Tarefa | Resp. | Depende de | Dias |
|---|---|---|---|---|
| E1.1 | Definir perguntas-alvo (ex.: "posso tomar X com Y?", "quais anti-hipertensivos são contraindicados na gravidez?") | P1, P5 | — | D1–D2 |
| E1.2 | Modelo conceitual: labels, relações e propriedades (proposta abaixo) | P1 | E1.1 | D2–D3 |
| E1.3 | Script Cypher do schema: constraints de unicidade, índices BTree, Fulltext e Vector | P1 | E0.2, E1.2 | D3–D4 |
| E1.4 | Grafo semente: 5 bulas inseridas à mão via Cypher | P1, P2 | E1.3 | D4–D5 |
| E1.5 | Documento de modelagem (diagrama + justificativas) para o artigo | P1 | E1.2 | D5 |

Proposta inicial de schema:

- Nós: `Medicamento` (nome comercial), `PrincipioAtivo`, `ClasseTerapeutica`, `Condicao` (doença/sintoma), `EfeitoAdverso`, `Fabricante`, `Populacao` (gestante, pediátrico, idoso, lactante), `Bula`, `Secao`, `Chunk` (texto + embedding).
- Relações: `(:Medicamento)-[:CONTEM {dose}]->(:PrincipioAtivo)`, `(:PrincipioAtivo)-[:PERTENCE_A]->(:ClasseTerapeutica)`, `(:Medicamento)-[:INDICADO_PARA]->(:Condicao)`, `(:Medicamento)-[:CONTRAINDICADO_EM]->(:Condicao|Populacao)`, `(:Medicamento)-[:PODE_CAUSAR {frequencia}]->(:EfeitoAdverso)`, `(:PrincipioAtivo)-[:INTERAGE_COM {gravidade, efeito}]->(:PrincipioAtivo)`, `(:Medicamento)-[:FABRICADO_POR]->(:Fabricante)`, `(:Bula)-[:TEM_SECAO]->(:Secao)-[:TEM_CHUNK]->(:Chunk)`.
- Proveniência: toda relação extraída guarda `fonte_chunk_id` e `confianca`; `(:Chunk)-[:MENCIONA]->(entidade)`.
- Índices: unicidade em `Medicamento.id`, `PrincipioAtivo.nome_canonico` etc.; Fulltext em nomes + sinônimos; Vector em `Chunk.embedding` e no embedding de nome das entidades.

## E2 — Corpus de bulas (P2) — D1–D8

| ID | Tarefa | Resp. | Depende de | Dias |
|---|---|---|---|---|
| E2.1 | Selecionar 50–100 bulas do Bulário Eletrônico da ANVISA (bula do profissional). Escolher classes que se cruzam (anti-hipertensivos, AINEs, anticoagulantes, antibióticos) para gerar interações multi-hop | P2 | E1.1 | D1–D3 |
| E2.2 | Download dos PDFs + metadados (fabricante, data, registro) | P2 | E2.1 | D2–D4 |
| E2.3 | Parser PDF → texto, separado por seção (Indicações, Contraindicações, Advertências, Interações, Reações adversas, Posologia) | P2 | E2.2 | D3–D6 |
| E2.4 | Chunking por seção, com IDs estáveis; saída em JSONL | P2 | E2.3 | D5–D7 |
| E2.5 | Anotar à mão entidades/relações de 5 bulas (gold set de extração) | P2, P3 | E2.3 | D6–D8 |

## E3 — Text-to-Graph: NER/RE (P3) — D4–D12

| ID | Tarefa | Resp. | Depende de | Dias |
|---|---|---|---|---|
| E3.1 | Modelos Pydantic das entidades/relações espelhando o schema | P3 | E1.2 | D4–D5 |
| E3.2 | Prompt de extração por seção, com saída estruturada, few-shot e campo de confiança | P3 | E3.1, E0.3 | D5–D8 |
| E3.3 | Validação: descartar relações fora do schema e tipos inválidos | P3 | E3.2 | D7–D9 |
| E3.4 | Rodar a extração no corpus inteiro, com cache/retry e controle de custo | P3 | E3.3, E2.4 | D9–D11 |
| E3.5 | Medir precisão/recall contra o gold set (E2.5) e ajustar o prompt | P3 | E3.2, E2.5 | D9–D12 |

## E4 — Resolução de entidades e ingestão (P4) — D5–D14

| ID | Tarefa | Resp. | Depende de | Dias |
|---|---|---|---|---|
| E4.1 | Normalização: minúsculas, acentos, sal/base ("losartana potássica" → "losartana"), dicionário de sinônimos (DCB) | P4 | E1.2 | D5–D8 |
| E4.2 | Matching por similaridade (fuzzy + embedding) para fundir duplicatas; limiar de corte documentado | P4 | E4.1, E0.3 | D7–D10 |
| E4.3 | Ingestão idempotente com `MERGE` em lote, gravando `fonte_chunk_id` e `confianca` | P4 | E1.3 | D6–D9 |
| E4.4 | Ingestão completa: chunks + entidades + relações + embeddings | P4 | E4.2, E4.3, E3.4 | D11–D13 |
| E4.5 | Relatório: nº de nós/relações antes e depois da resolução (métrica para o artigo) | P4 | E4.4 | D13–D14 |

## E5 — Retrieval híbrido e GraphRAG/KAG (P5) — D5–D19 — entrega Fase 3

Começa no grafo semente (E1.4); troca para o grafo completo depois de E4.4.

| ID | Tarefa | Resp. | Depende de | Dias |
|---|---|---|---|---|
| E5.1 | Busca vetorial: pergunta → chunks/entidades mais próximos (seeds) | P5 | E1.4 | D5–D8 |
| E5.2 | Expansão multi-hop em Cypher (2+ saltos a partir das seeds), com limite de nós | P5 | E5.1 | D7–D10 |
| E5.3 | Text-to-Cypher pelo LLM com schema no prompt; só leitura; validar com `EXPLAIN`; fallback para E5.2 | P5 | E5.1, E1.3 | D9–D13 |
| E5.4 | GDS: PageRank (ranquear nós do contexto), Louvain/Leiden (comunidades de efeitos/classes), Shortest Path (ligação entre dois medicamentos via princípio ativo/interação) | P5 | E1.4 | D10–D14 |
| E5.5 | Montador de contexto: subgrafo + trechos de bula, ordenado por PageRank | P5 | E5.2, E5.4 | D13–D15 |
| E5.6 | Geração da resposta: citar nós/caminhos usados; recusar quando o contexto não sustenta a resposta; score de confiança | P5 | E5.5, E5.3, E4.4 | D15–D18 |
| E5.7 | API única `responder(pergunta, modo)` → `{modo, resposta, subgrafo, cypher, nos, confianca, trechos}` | P5, P6 | E5.6 | D16–D19 |
| E5.8 | Modo `rag` (RAG tradicional): top-k no índice `chunk_embedding`, sem grafo, mesma geração de E5.6. Ver `docs/superpowers/specs/2026-10-23-visao-graphrag-vs-rag-design.md` | P5 | E5.6, E5.7 | D17–D19 |

## E6 — Interface e visualização (P6) — D6–D21

Começa com dados falsos no formato do contrato E5.7; integra o real em D17.

| ID | Tarefa | Resp. | Depende de | Dias |
|---|---|---|---|---|
| E6.1 | Fixar o contrato JSON de E5.7 com P5 (com campo `modo`) e criar mock dos dois modos | P6, P5 | E1.2 | D6–D7 |
| E6.2 | App Streamlit: chat + histórico | P6 | E6.1 | D7–D10 |
| E6.3 | Render interativo do subgrafo (pyvis ou streamlit-agraph); cor por label | P6 | E6.1 | D9–D13 |
| E6.4 | Painel de proveniência: nós consultados, Cypher gerado, confiança, trechos da bula com link para a fonte | P6 | E6.1 | D11–D15 |
| E6.5 | Integração com o backend real (E5.7) | P6, P5 | E5.7, E6.2–E6.4 | D17–D20 |
| E6.7 | Visão lado a lado: GraphRAG (subgrafo, Cypher) vs RAG tradicional (top-k trechos, scores) para a mesma pergunta | P6 | E6.3, E6.4, E5.8 | D18–D21 |
| E6.6 | Aviso "não substitui orientação médica", polimento, roteiro de demo | P6 | E6.5 | D20–D21 |

## E7 — Avaliação e testes (P2) — D8–D22

| ID | Tarefa | Resp. | Depende de | Dias |
|---|---|---|---|---|
| E7.1 | Gold set de 40 perguntas com resposta esperada: 1-hop, multi-hop e sem resposta (para medir alucinação) | P2, P1 | E1.1, E2.3 | D8–D12 |
| E7.2 | Testes pytest: parser, validação da extração, resolução, Cypher de leitura | Todos (cada um da sua parte) | — | D8–D20 |
| E7.3 | Baselines: LLM puro e RAG só vetorial (o RAG reutiliza o modo `rag` de E5.8) | P2 | E2.4, E0.3, E5.8 | D12–D19 |
| E7.4 | Rodar GraphRAG vs baselines: acurácia, fidelidade às fontes, taxa de alucinação, taxa de recusa correta | P2, P5 | E5.6, E7.1, E7.3 | D18–D21 |
| E7.5 | Tabelas e gráficos de resultado para o artigo | P2 | E7.4 | D21–D22 |

## E8 — Artigo, README e defesa (todos) — D14–D25 — entrega Fase 4

| ID | Tarefa | Resp. | Depende de | Dias |
|---|---|---|---|---|
| E8.1 | Esqueleto do artigo no template SBC; introdução e trabalhos relacionados | P1 | — | D14–D17 |
| E8.2 | Seções de método (modelagem, extração, resolução, retrieval, UI) | Dono de cada épico | E1.5, E3.5, E4.5, E5.6 | D17–D21 |
| E8.3 | Resultados e discussão (usa E7.5) | P2, P5 | E7.5 | D21–D23 |
| E8.4 | README: setup local com docker, variáveis, como ingerir, como rodar a UI; créditos às bibliotecas (LangChain, LlamaIndex, Neo4j GenAI SDK, etc.) | P4 | E6.5 | D20–D23 |
| E8.5 | Revisão final do artigo e do repo | P1, P3 | E8.2–E8.4 | D23–D24 |
| E8.6 | Slides, vídeo de demo como backup, ensaio da defesa | P6, todos | E6.6 | D22–D25 |

---

## Visão por dia (resumo)

| Dias | Foco |
|---|---|
| D1–D5 | Setup, schema, corpus, grafo semente (M1) |
| D5–D12 | Extração, resolução, ingestão; retrieval e UI no grafo semente (M2) |
| D12–D18 | Grafo completo; GraphRAG ponta a ponta; baselines (M3) |
| D18–D21 | Integração UI, avaliação, freeze (M4) |
| D21–D25 | Artigo, README, slides, defesa (M5) |

## Riscos

- **Custo/cota do LLM na extração (E3.4):** cachear respostas; testar com 10 bulas antes do corpus inteiro.
- **PDF de bula mal formatado (E2.3):** começar pelas bulas que parseiam limpo; não travar o pipeline por causa de poucas.
- **Text-to-Cypher gerando query inválida (E5.3):** fallback para a expansão fixa de E5.2.
- **Integração tardia (E6.5):** contrato JSON fixado em D7 e mock usado desde o início.
- **Grafo semente diferente do real:** P1 revisa o schema em D12 e avisa P5/P6 de qualquer mudança.
