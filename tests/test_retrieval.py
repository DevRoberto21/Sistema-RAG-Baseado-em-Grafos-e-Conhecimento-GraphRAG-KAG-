"""Retrieval E5.1 + E5.2 sobre o grafo semente. Pula sem Neo4j (fixture db em conftest.py)."""

from graphrag_bulas.retrieval import buscar_seeds, expandir, recuperar, termos_fulltext

MAREVAN_ADVIL = "Posso tomar Marevan com Advil?"


def ids_seeds(db, pergunta):
    return {s["id"] for s in buscar_seeds(db, pergunta)["entidades"]}


def test_termos_fulltext_ignora_palavras_curtas_e_especiais():
    assert (
        termos_fulltext('Posso tomar "Marevan" (com) Advil? AND/OR:') == "Posso tomar Marevan Advil"
    )


def test_seeds_marevan_advil_sem_ruido_vetorial(db):
    seeds = ids_seeds(db, MAREVAN_ADVIL)
    assert {"marevan", "advil"} <= seeds
    assert "enalapril" not in seeds  # vetor 0.70, abaixo do corte


def test_seed_aine_vem_do_fulltext(db):
    ents = {s["id"]: s for s in buscar_seeds(db, "Varfarina interage com algum AINE?")["entidades"]}
    assert "varfarina" in ents
    assert "fulltext" in ents["aine"]["fontes"]


def test_seeds_gravidez(db):
    seeds = ids_seeds(db, "Quais anti-hipertensivos são contraindicados na gravidez?")
    assert {"anti_hipertensivo", "gestante"} <= seeds


def test_chunks_seed_ordenados_e_com_fonte(db):
    chunks = buscar_seeds(db, MAREVAN_ADVIL, k_chunks=3)["chunks"]
    assert len(chunks) == 3
    assert [c["score"] for c in chunks] == sorted((c["score"] for c in chunks), reverse=True)
    assert all(c["fonte"].startswith("bula_") for c in chunks)


def test_pergunta_sem_palavras_nao_consulta(db):
    assert buscar_seeds(db, " ?! ") == {"entidades": [], "chunks": []}


def test_caracteres_especiais_do_lucene_nao_quebram(db):
    seeds = ids_seeds(db, 'Marevan "AND" (Advil) : / ~ * [AINE]?')
    assert {"marevan", "advil"} <= seeds


def test_caminho_marevan_advil(db):
    r = recuperar(db, MAREVAN_ADVIL)
    arestas = {(a["origem"], a["destino"], a["tipo"]) for a in r["subgrafo"]["arestas"]}
    assert ("varfarina", "aine", "INTERAGE_COM") in arestas
    assert ("ibuprofeno", "anticoagulante", "INTERAGE_COM") in arestas
    citados = [t["chunk_id"] for t in r["trechos"] if t["score"] is None]
    assert {"bula_marevan_interacoes_0", "bula_advil_interacoes_1"} <= set(citados)


def test_trechos_citados_antes_dos_chunks_seed(db):
    trechos = recuperar(db, MAREVAN_ADVIL)["trechos"]
    scores = [t["score"] for t in trechos]
    n_citados = scores.count(None)
    assert n_citados > 0
    assert all(s is None for s in scores[:n_citados])
    assert len({t["chunk_id"] for t in trechos}) == len(trechos)


def test_gravidez_cozaar_contraindicado(db):
    arestas = recuperar(db, "Quais anti-hipertensivos são contraindicados na gravidez?")[
        "subgrafo"
    ]["arestas"]
    assert any(
        a["origem"] == "cozaar" and a["destino"] == "gestante" and a["tipo"] == "CONTRAINDICADO_EM"
        for a in arestas
    )


def test_efeitos_comuns_losartana_enalapril(db):
    sub = recuperar(db, "Que efeitos losartana e enalapril têm em comum?")["subgrafo"]

    def efeitos(med):
        return {
            a["destino"]
            for a in sub["arestas"]
            if a["origem"] == med and a["tipo"] == "PODE_CAUSAR"
        }

    assert efeitos("cozaar") & efeitos("renitec")


def test_max_nos_mantem_seeds(db):
    seeds = buscar_seeds(db, MAREVAN_ADVIL)
    nos = expandir(db, seeds, max_nos=5)["subgrafo"]["nos"]
    assert len(nos) <= 5
    assert set(expandir(db, seeds, max_nos=5)["seeds"]) <= {n["id"] for n in nos}
    assert all(n["dist"] == 0 for n in nos if n["id"] in {"marevan", "advil"})


def test_nao_percorre_relacoes_de_documento(db):
    labels = {lb for n in recuperar(db, MAREVAN_ADVIL)["subgrafo"]["nos"] for lb in n["labels"]}
    assert not labels & {"Bula", "Secao", "Chunk"}


def test_so_leitura(db):
    def contagem():
        q = "MATCH (n) WITH count(n) AS n MATCH ()-[r]->() RETURN n, count(r) AS r"
        return dict(db.execute_query(q).records[0])

    antes = contagem()
    recuperar(db, MAREVAN_ADVIL)
    assert contagem() == antes


def test_recuperar_sem_llm_nao_gera_cypher(db):
    assert recuperar(db, MAREVAN_ADVIL)["cypher"] is None


def test_recuperar_com_llm_traz_linhas_do_cypher(db):
    from test_text2cypher import COZAAR, LLMFalso

    r = recuperar(db, MAREVAN_ADVIL, llm=LLMFalso(COZAAR))
    assert r["cypher"]["linhas"] and r["cypher"]["erro"] is None
    assert r["subgrafo"]["nos"]  # a expansão continua rodando
