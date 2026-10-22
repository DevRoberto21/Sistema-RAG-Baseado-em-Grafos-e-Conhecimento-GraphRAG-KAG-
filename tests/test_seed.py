"""Perguntas-alvo (docs/modelagem.md, seção 1) respondidas pelo grafo semente.

Precisa do Neo4j com cypher/schema.cypher e cypher/seed.cypher aplicados; senão é pulado.
"""


def consulta(driver, cypher, **params):
    return driver.execute_query(cypher, params).records


def test_interacao_marevan_advil_por_principio_ou_classe(db):
    rows = consulta(
        db,
        """
        MATCH (:Medicamento {id: $a})-[:CONTEM]->(p1), (:Medicamento {id: $b})-[:CONTEM]->(p2)
        MATCH (p1)-[:PERTENCE_A*0..1]->(x)-[i:INTERAGE_COM]-(y)<-[:PERTENCE_A*0..1]-(p2)
        RETURN DISTINCT i.fonte_chunk_id AS fonte
        """,
        a="marevan",
        b="advil",
    )
    assert {r["fonte"] for r in rows} == {"bula_marevan_interacoes_0", "bula_advil_interacoes_1"}


def test_anti_hipertensivos_contraindicados_na_gravidez(db):
    rows = consulta(
        db,
        """
        MATCH (:ClasseTerapeutica {id: 'anti_hipertensivo'})<-[:PERTENCE_A]-(:PrincipioAtivo)
              <-[:CONTEM]-(m:Medicamento)-[:CONTRAINDICADO_EM]->(:Populacao {id: 'gestante'})
        RETURN m.id AS id
        """,
    )
    # Renitec só "não recomenda" na gravidez; não é contraindicação na bula.
    assert [r["id"] for r in rows] == ["cozaar"]


def test_efeitos_comuns_losartana_enalapril(db):
    rows = consulta(
        db,
        """
        MATCH (:Medicamento {id: 'cozaar'})-[:PODE_CAUSAR]->(e:EfeitoAdverso)
              <-[:PODE_CAUSAR]-(:Medicamento {id: 'renitec'})
        RETURN e.id AS id
        """,
    )
    assert {"tontura", "cefaleia", "tosse", "angioedema", "hipercalemia"} <= {r["id"] for r in rows}


def test_indicados_para_hipertensao(db):
    rows = consulta(
        db,
        "MATCH (m:Medicamento)-[:INDICADO_PARA]->(:Condicao {id: 'hipertensao'}) RETURN m.id AS id",
    )
    assert {r["id"] for r in rows} == {"cozaar", "renitec"}


def test_sem_resposta_cozaar_alopecia(db):
    rows = consulta(
        db,
        """
        MATCH (m:Medicamento)-[:PODE_CAUSAR]->(:EfeitoAdverso {id: 'alopecia'})
        RETURN m.id AS id
        """,
    )
    assert "cozaar" not in {r["id"] for r in rows}


def test_toda_fonte_aponta_para_chunk(db):
    rows = consulta(
        db,
        """
        MATCH ()-[r]->() WHERE r.fonte_chunk_id IS NOT NULL
          AND NOT EXISTS { MATCH (:Chunk {id: r.fonte_chunk_id}) }
        RETURN count(r) AS n
        """,
    )
    assert rows[0]["n"] == 0


def test_fulltext_acha_sinonimo(db):
    rows = consulta(
        db,
        "CALL db.index.fulltext.queryNodes('entidade_nomes', 'mialgia') "
        "YIELD node RETURN node.id AS id",
    )
    assert "dor_muscular" in {r["id"] for r in rows}
