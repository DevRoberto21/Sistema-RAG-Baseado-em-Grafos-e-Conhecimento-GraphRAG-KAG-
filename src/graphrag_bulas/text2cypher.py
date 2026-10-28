"""Text-to-Cypher (E5.3): o LLM gera Cypher de leitura a partir da pergunta e das seeds.

Spec: docs/superpowers/specs/2026-10-28-e5-text2cypher-design.md
"""

import logging
import re

from pydantic import BaseModel, Field

from neo4j import READ_ACCESS, unit_of_work

log = logging.getLogger(__name__)

TIMEOUT_S = 5
MAX_LINHAS = 50
SEM_CONSULTA = "sem_consulta"
# Também rejeita essas palavras dentro de string literal: rejeição a mais, nunca escrita liberada.
# SHOW/TERMINATE etc. são comandos administrativos que o Neo4j reporta como query_type "r".
PROIBIDAS = re.compile(
    r"\b(CALL|LOAD|CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|FOREACH"
    r"|SHOW|TERMINATE|USE|ALTER|GRANT|DENY|REVOKE|START|STOP|APOC)\b",
    re.IGNORECASE,
)

REGRAS = """Você traduz perguntas sobre bulas de medicamentos em UMA consulta Cypher para o Neo4j.

Regras:
- Só leitura: use MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY e LIMIT. Nunca use
  CREATE, MERGE, SET, DELETE, REMOVE, DROP, CALL, FOREACH ou LOAD CSV.
- Use só os labels, relações e propriedades do schema abaixo.
- Filtre entidades por id, usando só os ids da lista de seeds. Escreva os ids literais, sem
  parâmetros ($).
- Leia INTERAGE_COM sem direção: (a)-[r:INTERAGE_COM]-(b).
- INTERAGE_COM pode apontar para uma ClasseTerapeutica. Para achar os princípios ativos dessa
  classe, desça por (classe)<-[:PERTENCE_A]-(pa:PrincipioAtivo).
- Ao retornar um fato de uma relação r, retorne também r.fonte_chunk_id.
- Retorne propriedades (m.nome, r.dose), nunca nós inteiros.
- Termine com LIMIT 50.
- Se o schema não responde à pergunta, devolva cypher vazio."""

# Manter em sincronia com docs/modelagem.md, seções 3 e 4.
SCHEMA = """Schema (todo nó abaixo também tem o label :Entidade).

Nós, todos com id, nome e sinonimos:
- Medicamento {registro_anvisa, generico: bool}
- PrincipioAtivo
- ClasseTerapeutica
- Condicao
- EfeitoAdverso
- Fabricante
- Populacao: id só pode ser 'gestante', 'lactante', 'pediatrico' ou 'idoso'

Relações, todas com fonte_chunk_id, confianca e metodo:
- (:Medicamento)-[:CONTEM {dose}]->(:PrincipioAtivo)
- (:PrincipioAtivo)-[:PERTENCE_A]->(:ClasseTerapeutica)
- (:Medicamento)-[:INDICADO_PARA]->(:Condicao)
- (:Medicamento)-[:CONTRAINDICADO_EM]->(:Condicao|Populacao)
- (:Medicamento)-[:PODE_CAUSAR {frequencia}]->(:EfeitoAdverso)
- (:PrincipioAtivo)-[:INTERAGE_COM {gravidade, efeito}]->(:PrincipioAtivo|ClasseTerapeutica)
- (:Medicamento)-[:FABRICADO_POR]->(:Fabricante)

frequencia: muito_comum, comum, incomum, rara, muito_rara, desconhecida.
gravidade: grave, moderada, leve, desconhecida."""

# Remédios fora do grafo semente: não vazam as perguntas-alvo nem o gold set do E7.
EXEMPLOS = """Exemplos:

Pergunta: Quais efeitos raros a Novalgina pode causar?
Seeds: novalgina (Medicamento): Novalgina
Cypher:
MATCH (m:Medicamento {id: 'novalgina'})-[r:PODE_CAUSAR]->(e:EfeitoAdverso)
WHERE r.frequencia IN ['rara', 'muito_rara']
RETURN e.nome AS efeito, r.frequencia AS frequencia, r.fonte_chunk_id AS fonte_chunk_id
LIMIT 50

Pergunta: Qual a dose de omeprazol no Losec?
Seeds: losec (Medicamento): Losec; omeprazol (PrincipioAtivo): Omeprazol
Cypher:
MATCH (m:Medicamento {id: 'losec'})-[r:CONTEM]->(p:PrincipioAtivo {id: 'omeprazol'})
RETURN m.nome AS medicamento, p.nome AS principio_ativo, r.dose AS dose,
       r.fonte_chunk_id AS fonte_chunk_id
LIMIT 50

Pergunta: Algum remédio com dipirona é contraindicado para idosos?
Seeds: dipirona (PrincipioAtivo): Dipirona; idoso (Populacao): Idoso
Cypher:
MATCH (m:Medicamento)-[:CONTEM]->(:PrincipioAtivo {id: 'dipirona'}),
      (m)-[r:CONTRAINDICADO_EM]->(po:Populacao {id: 'idoso'})
RETURN m.nome AS medicamento, po.nome AS populacao, r.fonte_chunk_id AS fonte_chunk_id
LIMIT 50

Pergunta: Qual a cor do comprimido de Losec?
Seeds: losec (Medicamento): Losec
Cypher: (vazio)"""

IDS_EXEMPLOS = ["novalgina", "losec", "omeprazol", "dipirona"]


class Consulta(BaseModel):
    cypher: str = Field(description="Consulta Cypher de leitura, ou vazio se o schema não responde")


class CypherInvalido(Exception):
    pass


def gerar_cypher(llm, pergunta, seeds, anterior=None, erro=None):
    """Monta o prompt e pede ao LLM uma Consulta. Não acessa o Neo4j."""
    linhas = [f"{s['id']} ({', '.join(s['labels'])}): {s['nome']}" for s in seeds]
    partes = [REGRAS, SCHEMA, EXEMPLOS, "Seeds:\n" + ("\n".join(linhas) or "nenhuma")]
    partes.append(f"Pergunta: {pergunta}")
    if erro:
        partes.append(
            f"A consulta anterior falhou. Corrija.\nCypher anterior: {anterior}\nErro: {erro}"
        )
    return llm.with_structured_output(Consulta).invoke("\n\n".join(partes)).cypher.strip()


def validar_cypher(driver, cypher):
    """Levanta CypherInvalido se a consulta for vazia, proibida, inválida ou não for só leitura."""
    if not cypher.strip():
        raise CypherInvalido(SEM_CONSULTA)
    if m := PROIBIDAS.search(cypher):
        raise CypherInvalido(f"palavra proibida: {m.group(0)}")
    try:
        with driver.session(default_access_mode=READ_ACCESS) as s:
            tipo = s.run("EXPLAIN " + cypher).consume().query_type
    except Exception as e:
        raise CypherInvalido(str(e)) from e
    if tipo != "r":
        raise CypherInvalido(f"consulta não é só leitura (tipo {tipo})")


def _sem_embedding(v):
    if isinstance(v, dict):
        return {k: _sem_embedding(x) for k, x in v.items() if not k.startswith("embedding")}
    if isinstance(v, list):
        return [_sem_embedding(x) for x in v]
    return v


@unit_of_work(timeout=TIMEOUT_S)
def _ler_linhas(tx, cypher):
    return [_sem_embedding(r.data()) for r in tx.run(cypher).fetch(MAX_LINHAS)]


def _falha(query, erro):
    log.warning("text2cypher falhou: %s | %s", erro, query)
    return {"query": query, "linhas": [], "erro": erro}


def consultar(driver, llm, pergunta, seeds, tentativas=2):
    """Gera, valida e executa o Cypher. Nunca levanta exceção; falha vai em "erro"."""
    cypher = erro = None
    for _ in range(tentativas):
        try:
            cypher = gerar_cypher(llm, pergunta, seeds, cypher, erro)
        except Exception as e:  # rede, cota ou saída inválida do LLM
            return _falha(None, f"llm: {e}")
        try:
            validar_cypher(driver, cypher)
            with driver.session(default_access_mode=READ_ACCESS) as s:
                linhas = s.execute_read(_ler_linhas, cypher)
        except CypherInvalido as e:
            if str(e) == SEM_CONSULTA:
                return _falha(None, SEM_CONSULTA)
            erro = str(e)
            continue
        except Exception as e:  # timeout ou erro na execução: sem nova tentativa
            return _falha(cypher, str(e))
        return {"query": cypher, "linhas": linhas, "erro": None}
    return _falha(cypher, erro)
