"""Geração da resposta (E5.6): cita o contexto, recusa sem suporte e calcula a confiança.

Spec: docs/superpowers/specs/2026-10-28-e5-contexto-geracao-api-design.md
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

PESO_SUPORTE = {"total": 1.0, "parcial": 0.6, "nenhum": 0.0}
RECUSA = "Não encontrei nas bulas informação suficiente para responder com segurança."

REGRAS = """Você responde perguntas sobre bulas de medicamentos.

Regras:
- Responda em português, só com o contexto abaixo, sem conhecimento próprio.
- Em chunks, liste os chunk_ids (entre colchetes no contexto) que sustentam a resposta. Em nos,
  liste os ids das entidades usadas (os ids aparecem em "ids:" nos fatos).
- suporte: total se o contexto sustenta toda a resposta, parcial se sustenta só parte, nenhum se
  não sustenta.
- Em pergunta sobre interação, contraindicação ou dose, oriente procurar médico ou farmacêutico."""

NOTA_SEM_CONSULTA = "A consulta estruturada indicou que o schema do grafo não cobre esta pergunta."


# suporte antes das listas e listas com teto: o qwen 7b repetia ids até o limite de saída e o
# JSON acabava sem suporte. O Ollama aplica a ordem e o maxItems do schema na decodificação.
class Resposta(BaseModel):
    resposta: str
    suporte: Literal["total", "parcial", "nenhum"]
    chunks: list[str] = Field(description="chunk_ids que sustentam a resposta", max_length=8)
    nos: list[str] = Field(description="ids das entidades usadas", max_length=12)


# Resposta que diz que o contexto não traz a informação, mas sem marcar suporte nenhum (s02 do E7).
SEM_INFO = re.compile(
    r"\bnão (há|consta|encontr|está (mencionad|presente)|menciona|posso|traz|fornece)", re.I
)


def _diz_que_nao_sabe(texto):
    primeira = re.split(r"(?<=[.!?])\s", texto.strip(), maxsplit=1)[0]
    return "contexto" in primeira.lower() and bool(SEM_INFO.search(primeira))


def _limpar(ids):
    """Ids citados sem colchetes; de uma linha inteira do contexto, os ids entre colchetes dela."""
    return [x.strip() for i in ids for x in (re.findall(r"\[([^\[\]]+)\]", i) or [i])]


def _recusa():
    return {"resposta": RECUSA, "chunks": [], "nos": [], "confianca": 0.0, "recusou": True}


def gerar_resposta(llm, pergunta, contexto):
    """Pede a Resposta ao LLM e confere as citações. Falha do LLM propaga."""
    if not contexto["texto"]:
        return _recusa()
    partes = [REGRAS]
    if contexto["sem_consulta"]:
        partes.append(NOTA_SEM_CONSULTA)
    partes += ["Contexto:\n" + contexto["texto"], f"Pergunta: {pergunta}"]
    r = llm.with_structured_output(Resposta).invoke("\n\n".join(partes))
    # O contexto mostra os chunk_ids entre colchetes e o modelo às vezes os copia junto.
    citados_c = list(dict.fromkeys(_limpar(r.chunks)))
    citados_n = list(dict.fromkeys(_limpar(r.nos)))
    chunks = [c for c in citados_c if c in contexto["chunk_ids"]]
    nos = [n for n in citados_n if n in contexto["nos"]]
    # Fato do grafo sem fonte_chunk_id (ex.: CONTEM) também sustenta: basta um nó válido.
    if r.suporte == "nenhum" or not (chunks or nos) or _diz_que_nao_sabe(r.resposta):
        return _recusa()
    # Sem nós no contexto (modo rag), ids de entidade citados não contam contra a confiança.
    citadas = len(citados_c) + (len(citados_n) if contexto["nos"] else 0)
    confianca = round(PESO_SUPORTE[r.suporte] * (len(chunks) + len(nos)) / citadas, 2)
    return {
        "resposta": r.resposta,
        "chunks": chunks,
        "nos": nos,
        "confianca": confianca,
        "recusou": False,
    }
