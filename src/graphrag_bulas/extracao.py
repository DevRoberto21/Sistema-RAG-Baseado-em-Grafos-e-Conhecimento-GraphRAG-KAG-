"""Extração NER/RE de um chunk por LLM (E3.2): prompt por seção, few-shot e saída estruturada.

A saída segue modelos.Extracao (E3.1), com `confianca` por relação. Descartar relações com
pontas de label errado é tarefa da validação (E3.3); rodar no corpus é E3.4.
"""

from graphrag_bulas.modelos import Entidade, Extracao, Relacao

REGRAS = """Você extrai entidades e relações de um trecho (chunk) de bula de medicamento da ANVISA.

Regras:
- Extraia só o que o trecho afirma. Não use conhecimento próprio nem complete o que falta.
- Toda origem e destino de relação é o id de uma entidade da sua lista de entidades.
- Liste em entidades só o que é ponta de alguma relação.
- O medicamento da bula já tem id definido (abaixo). Use esse id para ele.
- id: slug minúsculo, sem acento, com _ no lugar de espaço (insuficiencia_renal).
- PrincipioAtivo: id pelo nome DCB sem sal (losartana, não losartana potássica).
- Populacao: só gestante, lactante, pediatrico ou idoso. Gravidez vira gestante; amamentação vira
  lactante; criança vira pediatrico.
- Relações e pontas aceitas:
  (Medicamento)-[CONTEM {dose}]->(PrincipioAtivo)
  (PrincipioAtivo)-[PERTENCE_A]->(ClasseTerapeutica)
  (Medicamento)-[INDICADO_PARA]->(Condicao)
  (Medicamento)-[CONTRAINDICADO_EM]->(Condicao ou Populacao)
  (Medicamento)-[PODE_CAUSAR {frequencia}]->(EfeitoAdverso)
  (PrincipioAtivo)-[INTERAGE_COM {gravidade, efeito}]->(PrincipioAtivo ou ClasseTerapeutica)
  (Medicamento)-[FABRICADO_POR]->(Fabricante)
- frequencia: muito_comum, comum, incomum, rara, muito_rara ou desconhecida. Faixa ("incomum a
  comum") vira a mais frequente.
- gravidade: grave, moderada, leve ou desconhecida. Sem gravidade explícita, use desconhecida.
- efeito: curto, com as palavras da bula.
- Interação citando uma classe ("AINEs", "anticoagulantes") aponta para a ClasseTerapeutica.
- confianca: 1.0 se o trecho afirma o fato com todas as letras; 0.7 se afirma com ressalva ou
  exige ligar duas frases; 0.4 ou menos se é só sugerido.
- Trecho sem fato do schema: entidades e relacoes vazias."""

# O que procurar em cada Secao.tipo (chunks.TIPOS).
FOCO = {
    "indicacoes": "INDICADO_PARA: doenças e sintomas que o medicamento trata ou previne.",
    "contraindicacoes": "CONTRAINDICADO_EM: condições e populações em que o uso é proibido.",
    "advertencias": "CONTRAINDICADO_EM só quando o trecho proíbe o uso (\"não deve ser usado\"). "
    "Cuidado, ajuste de dose ou monitoramento não é contraindicação.",
    "interacoes": "INTERAGE_COM entre o princípio ativo da bula e outros fármacos ou classes. "
    "PERTENCE_A quando o trecho diz a classe de um fármaco.",
    "reacoes_adversas": "PODE_CAUSAR com a frequencia que o trecho dá a cada reação.",
    "posologia": "CONTEM com a dose, se o trecho disser. Esquema de doses não é relação.",
}

# Fora do gold set (E2.5), para não vazar a resposta na medição (E3.5). Trechos parafraseados.
EXEMPLOS = [
    (
        "losec", "indicacoes",
        "Losec é indicado para o tratamento de úlcera duodenal e da esofagite de refluxo.",
        Extracao(
            entidades=[
                Entidade(id="losec", label="Medicamento", nome="Losec"),
                Entidade(id="ulcera_duodenal", label="Condicao", nome="Úlcera duodenal"),
                Entidade(id="esofagite_de_refluxo", label="Condicao", nome="Esofagite de refluxo"),
            ],
            relacoes=[
                Relacao(tipo="INDICADO_PARA", origem="losec", destino="ulcera_duodenal",
                        confianca=1.0),
                Relacao(tipo="INDICADO_PARA", origem="losec", destino="esofagite_de_refluxo",
                        confianca=1.0),
            ],
        ),
    ),
    (
        "novalgina", "contraindicacoes",
        "Novalgina não deve ser utilizada durante os três primeiros meses de gravidez nem por "
        "pacientes com porfiria hepática aguda intermitente.",
        Extracao(
            entidades=[
                Entidade(id="novalgina", label="Medicamento", nome="Novalgina"),
                Entidade(id="gestante", label="Populacao", nome="Gestante"),
                Entidade(id="porfiria_hepatica_aguda_intermitente", label="Condicao",
                         nome="Porfiria hepática aguda intermitente"),
            ],
            relacoes=[
                Relacao(tipo="CONTRAINDICADO_EM", origem="novalgina", destino="gestante",
                        confianca=1.0),
                Relacao(tipo="CONTRAINDICADO_EM", origem="novalgina",
                        destino="porfiria_hepatica_aguda_intermitente", confianca=1.0),
            ],
        ),
    ),
    (
        "losec", "interacoes",
        "O omeprazol pode reduzir a absorção do cetoconazol. O uso com clopidogrel diminui a "
        "inibição plaquetária e não é recomendado.",
        Extracao(
            entidades=[
                Entidade(id="omeprazol", label="PrincipioAtivo", nome="Omeprazol"),
                Entidade(id="cetoconazol", label="PrincipioAtivo", nome="Cetoconazol"),
                Entidade(id="clopidogrel", label="PrincipioAtivo", nome="Clopidogrel"),
            ],
            relacoes=[
                Relacao(tipo="INTERAGE_COM", origem="omeprazol", destino="cetoconazol",
                        gravidade="desconhecida", efeito="redução da absorção do cetoconazol",
                        confianca=1.0),
                Relacao(tipo="INTERAGE_COM", origem="omeprazol", destino="clopidogrel",
                        gravidade="desconhecida", efeito="diminui a inibição plaquetária",
                        confianca=1.0),
            ],
        ),
    ),
    (
        "novalgina", "reacoes_adversas",
        "Reação rara (> 1/10.000 e < 1/1.000): agranulocitose. Pode ocorrer hipotensão "
        "transitória isolada (reação incomum).",
        Extracao(
            entidades=[
                Entidade(id="novalgina", label="Medicamento", nome="Novalgina"),
                Entidade(id="agranulocitose", label="EfeitoAdverso", nome="Agranulocitose"),
                Entidade(id="hipotensao", label="EfeitoAdverso", nome="Hipotensão"),
            ],
            relacoes=[
                Relacao(tipo="PODE_CAUSAR", origem="novalgina", destino="agranulocitose",
                        frequencia="rara", confianca=1.0),
                Relacao(tipo="PODE_CAUSAR", origem="novalgina", destino="hipotensao",
                        frequencia="incomum", confianca=1.0),
            ],
        ),
    ),
    (
        "losec", "posologia",
        "Tomar uma cápsula de manhã, antes do café, durante 4 semanas.",
        Extracao(entidades=[], relacoes=[]),
    ),
]


def _exemplo(med, tipo, texto, saida):
    return (f"Medicamento da bula: {med}\nSeção: {tipo}\nTrecho: {texto}\n"
            f"Saída: {saida.model_dump_json(exclude_none=True)}")


def montar_prompt(chunk):
    """Prompt de um chunk de chunks.jsonl (E2.4): regras, foco da seção, exemplos e o trecho."""
    med = chunk["bula"].removeprefix("bula_")
    exemplos = "\n\n".join(_exemplo(*e) for e in EXEMPLOS)
    return "\n\n".join([
        REGRAS,
        "Exemplos:\n\n" + exemplos,
        f"Medicamento da bula: {med}\nSeção: {chunk['tipo']}\nFoco: {FOCO[chunk['tipo']]}\n"
        f"Trecho: {chunk['texto']}",
    ])


def extrair(llm, chunk) -> Extracao:
    """Pede ao LLM a Extracao de um chunk. Falha do LLM propaga (cache/retry ficam no E3.4)."""
    return llm.with_structured_output(Extracao).invoke(montar_prompt(chunk))
