"""Verifica Neo4j (+APOC/GDS) e o LLM. Uso: uv run python scripts/check_setup.py"""

import sys

from graphrag_bulas import config

ok = True

try:
    with config.get_driver() as driver, driver.session() as s:
        apoc = s.run("RETURN apoc.version() AS v").single()["v"]
        gds = s.run("RETURN gds.version() AS v").single()["v"]
    print(f"[ok] Neo4j  APOC {apoc}  GDS {gds}")
except Exception as e:
    ok = False
    print(f"[falha] Neo4j: {e}")

try:
    reply = config.get_llm(temperature=0).invoke("Responda só: ok")
    print(f"[ok] LLM {config.LLM_PROVIDER}/{config.LLM_MODEL}: {reply.text!r}")
except Exception as e:
    ok = False
    print(f"[falha] LLM: {e}")

sys.exit(0 if ok else 1)
