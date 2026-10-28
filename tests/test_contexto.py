"""Montador de contexto (E5.5). Função pura: r montado à mão, sem Neo4j."""

import datetime

from graphrag_bulas.contexto import montar_contexto


def aresta(origem, tipo, destino, fonte=None, confianca=1.0, **props):
    p = {"confianca": confianca, "metodo": "manual", **props}
    if fonte:
        p["fonte_chunk_id"] = fonte
    return {"origem": origem, "tipo": tipo, "destino": destino, "props": p}


def trecho(cid, score=None):
    return {"chunk_id": cid, "texto": f"texto de {cid}", "fonte": "bula_x", "score": score}


def r_base(arestas=(), trechos=(), cypher=None):
    nos = [
        {"id": "marevan", "nome": "Marevan", "labels": ["Medicamento"], "dist": 0},
        {"id": "varfarina", "nome": "Varfarina", "labels": ["PrincipioAtivo"], "dist": 1},
        {"id": "aine", "nome": "AINEs", "labels": ["ClasseTerapeutica"], "dist": 2},
    ]
    return {
        "seeds": ["marevan"],
        "subgrafo": {"nos": nos, "arestas": list(arestas)},
        "trechos": list(trechos),
        "cypher": cypher,
    }


def test_fato_tem_nomes_props_fonte_e_ids_sem_props_internas():
    r = r_base([aresta("marevan", "CONTEM", "varfarina", "c1", dose="5 mg")])
    texto = montar_contexto(r)["texto"]
    linha = "- Marevan -[CONTEM {dose: 5 mg}]-> Varfarina [c1] (ids: marevan, varfarina)"
    assert linha in texto
    assert "confianca" not in texto and "metodo" not in texto and "fonte_chunk_id" not in texto


def test_fatos_ordenados_por_dist_e_confianca_e_cortados():
    r = r_base(
        [
            aresta("varfarina", "INTERAGE_COM", "aine", "c3"),  # dist 1
            aresta("marevan", "PODE_CAUSAR", "x", "c2", confianca=0.5),  # dist 0
            aresta("marevan", "CONTEM", "varfarina", "c1", confianca=0.9),  # dist 0
        ]
    )
    ctx = montar_contexto(r, max_fatos=2)
    assert ctx["texto"].index("CONTEM") < ctx["texto"].index("PODE_CAUSAR")
    assert "INTERAGE_COM" not in ctx["texto"]
    assert ctx["nos"] == {"marevan", "varfarina", "x"}
    assert ctx["chunk_ids"] == {"c1", "c2"}


def test_trechos_citados_pelos_fatos_vem_primeiro_e_sao_cortados():
    r = r_base(
        [aresta("marevan", "CONTEM", "varfarina", "c1")],
        [trecho("s1", 0.9), trecho("s2", 0.8), trecho("c1"), trecho("s3", None)],
    )
    ctx = montar_contexto(r, max_trechos=3)
    assert [t["chunk_id"] for t in ctx["trechos"]] == ["c1", "s1", "s2"]
    assert ctx["texto"].index("[c1] (bula_x) texto de c1") < ctx["texto"].index("[s1]")


def test_linhas_do_cypher_entram_so_sem_erro():
    linha = {"medicamento": "Advil", "fonte_chunk_id": "c9"}
    ok = montar_contexto(r_base(cypher={"query": "q", "linhas": [linha], "erro": None}))
    assert '- {"fonte_chunk_id": "c9", "medicamento": "Advil"}' in ok["texto"]
    assert "c9" in ok["chunk_ids"]
    erro = montar_contexto(r_base(cypher={"query": "q", "linhas": [linha], "erro": "x"}))
    assert "Cypher" not in erro["texto"]


def test_linha_com_data_e_fonte_nao_textual_nao_quebra():
    linha = {"data": datetime.date(2020, 1, 2), "fonte_chunk_id": ["c1"]}
    ctx = montar_contexto(r_base(cypher={"query": "q", "linhas": [linha], "erro": None}))
    assert "2020-01-02" in ctx["texto"]
    assert ctx["chunk_ids"] == set()


def test_sem_consulta():
    r = r_base(cypher={"query": None, "linhas": [], "erro": "sem_consulta"})
    assert montar_contexto(r)["sem_consulta"] is True
    assert montar_contexto(r_base())["sem_consulta"] is False


def test_contexto_vazio():
    ctx = montar_contexto(r_base())
    assert ctx["texto"] == "" and ctx["chunk_ids"] == set() and ctx["nos"] == set()


def test_contexto_do_semente_traz_a_interacao_marevan_advil(db):
    # Guarda dos limites: se o grafo crescer (M2) e a interação sair do contexto, reveja o corte.
    from graphrag_bulas.retrieval import recuperar

    ctx = montar_contexto(recuperar(db, "Posso tomar Marevan com Advil?"))
    assert {"bula_marevan_interacoes_0", "bula_advil_interacoes_1"} <= ctx["chunk_ids"]
    assert "- Varfarina -[INTERAGE_COM" in ctx["texto"]
