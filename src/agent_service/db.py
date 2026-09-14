"""Instância compartilhada do banco (memória comum, sessões, tracing, knowledge)."""

from functools import lru_cache

from agno.db.postgres import PostgresDb

from agent_service.config import get_settings


@lru_cache
def get_db() -> PostgresDb:
    settings = get_settings()
    return PostgresDb(db_url=settings.database_url)
