"""Configurações centrais do microserviço, carregadas de variáveis de ambiente."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Servidor
    app_name: str = "agent-service"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Banco de dados (memória comum, sessões, tracing, knowledge)
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/agent_service"

    # Redis (mensageria assíncrona / cache de sessão)
    redis_url: str = "redis://localhost:6379/0"
    redis_stream_tasks: str = "agent-service:tasks"
    redis_consumer_group: str = "agent-service:workers"

    # Provedor de modelo padrão
    default_model_provider: str = "google"
    default_model_id: str = "gemini-2.5-flash"
    google_api_key: str | None = None

    # Mem0 (camada de memória semântica opcional)
    mem0_api_key: str | None = None
    mem0_enabled: bool = False

    # Observabilidade
    langsmith_api_key: str | None = None
    langsmith_project: str = "agent-service"
    langsmith_tracing_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
