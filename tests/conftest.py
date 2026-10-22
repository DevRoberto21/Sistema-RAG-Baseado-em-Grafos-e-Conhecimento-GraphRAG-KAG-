"""Fixture db: Neo4j com o grafo semente; pula o teste se faltar."""

import pytest

from graphrag_bulas.config import get_driver


@pytest.fixture(scope="module")
def db():
    driver = get_driver()
    try:
        driver.verify_connectivity()
    except Exception:
        pytest.skip("Neo4j indisponível")
    if not driver.execute_query(
        "MATCH (m:Medicamento {id: 'cozaar'}) RETURN count(m) AS n"
    ).records[0]["n"]:
        pytest.skip("grafo semente não carregado")
    yield driver
    driver.close()
