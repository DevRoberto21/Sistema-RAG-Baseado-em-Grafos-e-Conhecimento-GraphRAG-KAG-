"""Retrieval do GraphRAG (E5.1 + E5.2): seeds híbridas e expansão multi-hop. Só leitura.

Spec: docs/superpowers/specs/2026-10-28-e5-retrieval-seeds-expansao-design.md
"""

import re

# Limiares calibrados na sondagem de 2026-10-28 sobre o grafo semente; recalibrar após o M2.
MIN_SCORE_VETOR = 0.75  # acertos ~0.79-0.83, ruído ~0.66-0.73
MIN_LETRAS_TERMO = 4  # índice sem stopwords: "a"/"de" casariam com fabricante e sinônimos
TOP_VETOR = 10
TOP_FULLTEXT = 10
RELACOES_DOMINIO = [
    "CONTEM",
    "PERTENCE_A",
    "INTERAGE_COM",
    "INDICADO_PARA",
    "CONTRAINDICADO_EM",
    "PODE_CAUSAR",
    "FABRICADO_POR",
]


def _ler(driver, cypher, **params):
    return driver.execute_query(cypher, params, routing_="r").records


def termos_fulltext(pergunta):
    """Palavras com 4+ letras, unidas por espaço (OR no Lucene).

    \\w+ já remove os caracteres especiais do Lucene, e o filtro de tamanho remove AND/OR/NOT.
    """
    return " ".join(w for w in re.findall(r"\w+", pergunta) if len(w) >= MIN_LETRAS_TERMO)
