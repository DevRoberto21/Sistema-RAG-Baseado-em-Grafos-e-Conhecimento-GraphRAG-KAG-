from graphrag_bulas import config


def test_config_defaults_present():
    assert config.NEO4J_URI.startswith("bolt://")
    assert config.LLM_PROVIDER and config.LLM_MODEL and config.EMBEDDING_MODEL
