"""Extração NER/RE de um chunk por LLM (E3.2): prompt por seção, few-shot e saída estruturada.

A saída segue modelos.Extracao (E3.1), com `confianca` por relação. `validar` (E3.3) limpa o
que o schema não aceita; rodar no corpus é E3.4.
"""

import re

from graphrag_bulas.chunks import slug
from graphrag_bulas.modelos import POPULACOES, RELACOES, Entidade, Extracao, Relacao

REGRAS = """Você extrai entidades e relações de um trecho (chunk) de bula de medicamento da ANVISA.

Regras:
- Extraia só o que o trecho afirma. Não use conhecimento próprio nem complete o que falta.
- Toda origem e destino de relação é o id de uma entidade da sua lista de entidades.
- Liste em entidades só o que é ponta de alguma relação.
- O medicamento da bula já tem id definido (abaixo). Use esse id para ele.
- id: slug minúsculo, sem acento, com _ no lugar de espaço (insuficiencia_renal).
- id em português, com as palavras inteiras da bula (hiperaldosteronismo_primario, não
  hiperaldosteronismo_prima).
- Condicao é doença ou estado do paciente, nunca substância: "intolerância à galactose", não
  "galactose".
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
- Uso proibido só junto com outro fármaco ("com X, contraindicado em Y") não é CONTRAINDICADO_EM
  Y: vira INTERAGE_COM do princípio ativo com X, gravidade grave.
- Interação citando uma classe ("AINEs", "anticoagulantes") aponta para a ClasseTerapeutica.
- confianca: 1.0 se o trecho afirma o fato com todas as letras; 0.7 se afirma com ressalva ou
  exige ligar duas frases; 0.4 ou menos se é só sugerido.
- Trecho sem fato do schema: entidades e relacoes vazias."""

# O que procurar em cada Secao.tipo (chunks.TIPOS).
FOCO = {
    "indicacoes": "INDICADO_PARA: doenças e sintomas que o medicamento trata ou previne.",
    "contraindicacoes": "CONTRAINDICADO_EM: condições e populações em que o uso é proibido.",
    "advertencias": "CONTRAINDICADO_EM só quando o trecho proíbe o uso (\"não deve ser usado\", "
    "confianca 1.0) ou desaconselha (\"não é recomendado\", confianca 0.7). Cautela, atenção, "
    "falta de dados, ajuste de dose ou monitoramento não é contraindicação: sem relação.",
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
        "pacientes com porfiria hepática aguda intermitente. O uso de dipirona com metotrexato é "
        "contraindicado em pacientes com insuficiência renal.",
        Extracao(
            entidades=[
                Entidade(id="novalgina", label="Medicamento", nome="Novalgina"),
                Entidade(id="gestante", label="Populacao", nome="Gestante"),
                Entidade(id="porfiria_hepatica_aguda_intermitente", label="Condicao",
                         nome="Porfiria hepática aguda intermitente"),
                Entidade(id="dipirona", label="PrincipioAtivo", nome="Dipirona"),
                Entidade(id="metotrexato", label="PrincipioAtivo", nome="Metotrexato"),
            ],
            relacoes=[
                Relacao(tipo="CONTRAINDICADO_EM", origem="novalgina", destino="gestante",
                        confianca=1.0),
                Relacao(tipo="CONTRAINDICADO_EM", origem="novalgina",
                        destino="porfiria_hepatica_aguda_intermitente", confianca=1.0),
                Relacao(tipo="INTERAGE_COM", origem="dipirona", destino="metotrexato",
                        gravidade="grave", efeito="contraindicado em insuficiência renal",
                        confianca=1.0),
            ],
        ),
    ),
    (
        "novalgina", "advertencias",
        "Pacientes com asma têm maior risco de reações anafilactoides; use com cautela. Em idosos, "
        "monitorar a função renal. Novalgina não deve ser usada por pacientes com deficiência de "
        "glicose-6-fosfato-desidrogenase. Contém sacarose: não deve ser usado por pessoas com "
        "intolerância à frutose.",
        Extracao(
            entidades=[
                Entidade(id="novalgina", label="Medicamento", nome="Novalgina"),
                Entidade(id="deficiencia_de_glicose_6_fosfato_desidrogenase", label="Condicao",
                         nome="Deficiência de glicose-6-fosfato-desidrogenase"),
                Entidade(id="intolerancia_a_frutose", label="Condicao",
                         nome="Intolerância à frutose"),
            ],
            relacoes=[
                Relacao(tipo="CONTRAINDICADO_EM", origem="novalgina",
                        destino="deficiencia_de_glicose_6_fosfato_desidrogenase", confianca=1.0),
                Relacao(tipo="CONTRAINDICADO_EM", origem="novalgina",
                        destino="intolerancia_a_frutose", confianca=1.0),
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


# Princípios ativos de cada bula, da composição (fora dos chunks; fonte do CONTEM no E4).
# Conferido: cada id aparece no texto da bula.
COMPOSICAO = {
    "advil": ["ibuprofeno"], "aldactone": ["espironolactona"], "amoxil": ["amoxicilina"],
    "ancoron": ["amiodarona"], "aradois": ["losartana"], "arcoxia": ["etoricoxibe"],
    "aspirina": ["acido_acetilsalicilico"], "atenolol": ["atenolol"],
    "bactrim": ["sulfametoxazol", "trimetoprima"], "benicar": ["olmesartana"],
    "brilinta": ["ticagrelor"], "carbolitium": ["litio"], "cataflam": ["diclofenaco"],
    "celebra": ["celecoxibe"], "cipro": ["ciprofloxacino"],
    "clavulin": ["amoxicilina", "clavulanato"], "clexane": ["enoxaparina"],
    "cozaar": ["losartana"], "flagyl": ["metronidazol"], "keflex": ["cefalexina"],
    "lasix": ["furosemida"], "marevan": ["varfarina"], "norvasc": ["anlodipino"],
    "renitec": ["enalapril"], "tylenol": ["paracetamol"],
}

# Sinônimos que o LLM usa para as 4 populações.
POP_SINONIMOS = {
    "gravidez": "gestante", "gravida": "gestante", "gravidas": "gestante",
    "gestacao": "gestante", "gestantes": "gestante",
    "lactacao": "lactante", "amamentacao": "lactante", "aleitamento": "lactante",
    "lactantes": "lactante",
    "crianca": "pediatrico", "criancas": "pediatrico", "pacientes_pediatricos": "pediatrico",
    "pediatria": "pediatrico",
    "idosos": "idoso", "geriatria": "idoso",
}

# Propriedade -> único tipo de relação que a aceita.
PROPS = {"frequencia": "PODE_CAUSAR", "gravidade": "INTERAGE_COM", "efeito": "INTERAGE_COM",
         "dose": "CONTEM"}


# Proibição explícita; "cautela", "não é recomendado" e risco-benefício não contam (gold E3.5).
PROIBE = re.compile(r"contra-?indica|não deve(m)? (ser )?(usad|utilizad|tomad|administrad)"
                    r"|não (use|utilize|tome)", re.I)


def validar(extracao: Extracao, med: str, chunk: dict | None = None
            ) -> tuple[Extracao, list[str]]:
    """Descarta o que o schema não aceita (E3.3). Devolve a extração limpa e os motivos.

    Tipo, label, vocabulário e faixa de confianca já são barrados pelo Pydantic (E3.1).
    Aqui: ids viram slug; sinônimo de Populacao vira uma das 4 e o resto sai; sai Medicamento
    que não é o da bula, relação com ponta ausente, de label errado ou laço; propriedade em
    relação errada é apagada; relação repetida fica com a maior confianca; entidade sem
    relação sai. Bula de um só princípio ativo: INTERAGE_COM/PERTENCE_A que o LLM pôs no
    Medicamento passa para o princípio ativo, e CONTRAINDICADO_EM com fármaco ou classe vira
    INTERAGE_COM grave (regra "com X, contraindicado"). Com o chunk: CONTRAINDICADO_EM fora
    da seção de contraindicações sai se o texto não tem proibição explícita (PROIBE).
    """
    sem_proibicao = bool(chunk) and chunk["tipo"] != "contraindicacoes" and not PROIBE.search(
        chunk["texto"])
    descartes, ents, nomes = [], {}, {}
    for e in extracao.entidades:
        i = slug(e.id)
        if e.label == "Populacao":
            nomes[i] = POP_SINONIMOS.get(i, i)
        e = e.model_copy(update={"id": nomes.get(i, i)})
        if e.label == "Populacao" and e.id not in POPULACOES:
            descartes.append(f"Populacao {e.id!r} fora de {sorted(POPULACOES)}")
        elif e.label == "Medicamento" and e.id != med:
            descartes.append(f"Medicamento {e.id!r} não é o da bula ({med!r})")
        else:
            ents.setdefault(e.id, e)
    pas = COMPOSICAO.get(med, [])
    rels = {}
    for r in extracao.relacoes:
        r = r.model_copy(update={"origem": nomes.get(slug(r.origem), slug(r.origem)),
                                 "destino": nomes.get(slug(r.destino), slug(r.destino))})
        o, d = ents.get(r.origem), ents.get(r.destino)
        if len(pas) == 1 and o and o.label == "Medicamento" and d and d.label in (
                "PrincipioAtivo", "ClasseTerapeutica") and not r.destino.startswith(pas[0]):
            # destino = o próprio princípio ativo (olmesartana_medoxomila): é alergia, não interação
            if r.tipo == "CONTRAINDICADO_EM":
                r = r.model_copy(update={"tipo": "INTERAGE_COM", "gravidade": "grave"})
            if r.tipo in ("INTERAGE_COM", "PERTENCE_A"):
                o = ents.setdefault(pas[0], Entidade(id=pas[0], label="PrincipioAtivo",
                                                     nome=pas[0]))
                r = r.model_copy(update={"origem": o.id})
        origens, destinos = RELACOES[r.tipo]
        onde = f"{r.tipo} {r.origem}->{r.destino}"
        if not o or not d:
            descartes.append(f"{onde}: ponta fora das entidades")
        elif o.label not in origens or d.label not in destinos:
            descartes.append(f"{onde}: pontas {o.label}->{d.label} fora do schema")
        elif r.origem == r.destino:
            descartes.append(f"{onde}: laço")
        elif r.tipo == "CONTRAINDICADO_EM" and sem_proibicao:
            descartes.append(f"{onde}: chunk sem proibição explícita")
        else:
            limpa = {p: None for p, tipo in PROPS.items() if tipo != r.tipo and getattr(r, p)}
            descartes += [f"{onde}: {p} apagada" for p in limpa]
            if r.tipo == "PODE_CAUSAR" and not r.frequencia:
                limpa["frequencia"] = "desconhecida"
            if r.tipo == "INTERAGE_COM" and not r.gravidade:
                limpa["gravidade"] = "desconhecida"
            r = r.model_copy(update=limpa)
            chave = (r.tipo, r.origem, r.destino)
            if chave in rels:
                descartes.append(f"{onde}: repetida")
            if chave not in rels or r.confianca > rels[chave].confianca:
                rels[chave] = r
    usadas = {i for r in rels.values() for i in (r.origem, r.destino)}
    return Extracao(entidades=[e for i, e in ents.items() if i in usadas],
                    relacoes=list(rels.values())), descartes
