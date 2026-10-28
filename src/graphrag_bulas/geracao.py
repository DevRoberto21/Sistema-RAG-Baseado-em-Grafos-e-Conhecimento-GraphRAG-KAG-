"""Geração da resposta (E5.6): cita o contexto, recusa sem suporte e calcula a confiança.

Spec: docs/superpowers/specs/2026-10-28-e5-contexto-geracao-api-design.md
"""

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


class Resposta(BaseModel):
    resposta: str
    chunks: list[str] = Field(description="chunk_ids que sustentam a resposta")
    nos: list[str] = Field(description="ids das entidades usadas")
    suporte: Literal["total", "parcial", "nenhum"]


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
    chunks = [c for c in dict.fromkeys(r.chunks) if c in contexto["chunk_ids"]]
    nos = [n for n in dict.fromkeys(r.nos) if n in contexto["nos"]]
    if r.suporte == "nenhum" or not chunks:
        return _recusa()
    citadas = len(set(r.chunks)) + len(set(r.nos))
    confianca = round(PESO_SUPORTE[r.suporte] * (len(chunks) + len(nos)) / citadas, 2)
    return {
        "resposta": r.resposta,
        "chunks": chunks,
        "nos": nos,
        "confianca": confianca,
        "recusou": False,
    }
