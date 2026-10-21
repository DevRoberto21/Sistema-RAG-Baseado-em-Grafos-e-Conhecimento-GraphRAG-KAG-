"""Configuração única do projeto, lida do .env."""

import os

from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "google_genai")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.8-flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")


def get_driver():
    from neo4j import GraphDatabase

    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def get_llm(**kwargs):
    """Troca de provedor = trocar LLM_PROVIDER/LLM_MODEL no .env."""
    from langchain.chat_models import init_chat_model

    return init_chat_model(LLM_MODEL, model_provider=LLM_PROVIDER, **kwargs)
