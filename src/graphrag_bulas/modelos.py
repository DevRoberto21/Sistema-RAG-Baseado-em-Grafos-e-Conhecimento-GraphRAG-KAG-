"""Modelos Pydantic das entidades e relações extraídas de um chunk (E3.1).

Espelham docs/modelagem.md, seções 3 e 4. São o schema da saída estruturada do LLM
(E3.2). Checar se as pontas de cada relação têm o label certo é tarefa da validação (E3.3).
"""

from typing import Literal, get_args

from pydantic import BaseModel, Field

Label = Literal[
    "Medicamento", "PrincipioAtivo", "ClasseTerapeutica", "Condicao",
    "EfeitoAdverso", "Fabricante", "Populacao",
]
TipoRelacao = Literal[
    "CONTEM", "PERTENCE_A", "INDICADO_PARA", "CONTRAINDICADO_EM",
    "PODE_CAUSAR", "INTERAGE_COM", "FABRICADO_POR",
]
Frequencia = Literal["muito_comum", "comum", "incomum", "rara", "muito_rara", "desconhecida"]
Gravidade = Literal["grave", "moderada", "leve", "desconhecida"]

LABELS = set(get_args(Label))
POPULACOES = {"gestante", "lactante", "pediatrico", "idoso"}
RELACOES: dict[str, tuple[set[str], set[str]]] = {  # tipo -> (labels de origem, de destino)
    "CONTEM": ({"Medicamento"}, {"PrincipioAtivo"}),
    "PERTENCE_A": ({"PrincipioAtivo"}, {"ClasseTerapeutica"}),
    "INDICADO_PARA": ({"Medicamento"}, {"Condicao"}),
    "CONTRAINDICADO_EM": ({"Medicamento"}, {"Condicao", "Populacao"}),
    "PODE_CAUSAR": ({"Medicamento"}, {"EfeitoAdverso"}),
    "INTERAGE_COM": ({"PrincipioAtivo"}, {"PrincipioAtivo", "ClasseTerapeutica"}),
    "FABRICADO_POR": ({"Medicamento"}, {"Fabricante"}),
}
assert set(RELACOES) == set(get_args(TipoRelacao))
VOCAB = {"frequencia": set(get_args(Frequencia)), "gravidade": set(get_args(Gravidade))}


class Entidade(BaseModel):
    id: str = Field(
        description="slug minúsculo, sem acento, com _ (ex.: insuficiencia_renal); "
        "princípio ativo pelo nome DCB sem sal (losartana, não losartana potássica); "
        "Populacao só gestante, lactante, pediatrico ou idoso"
    )
    label: Label
    nome: str = Field(description="forma de exibição, como aparece na bula")


class Relacao(BaseModel):
    tipo: TipoRelacao
    origem: str = Field(description="id de uma entidade da lista")
    destino: str = Field(description="id de uma entidade da lista")
    frequencia: Frequencia | None = Field(None, description="só PODE_CAUSAR")
    gravidade: Gravidade | None = Field(None, description="só INTERAGE_COM")
    efeito: str | None = Field(None, description="só INTERAGE_COM; curto, palavras da bula")
    dose: str | None = Field(None, description="só CONTEM (ex.: 50 mg)")
    confianca: float = Field(ge=0, le=1, description="o quanto o texto sustenta a relação")


class Extracao(BaseModel):
    """Fatos do schema afirmados num chunk. Vazio se o chunk não afirma nenhum."""

    entidades: list[Entidade]
    relacoes: list[Relacao]
