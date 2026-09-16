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

    # Observabilidade — Langfuse (sem as duas chaves, o tracing vira no-op)
    langfuse_enabled: bool = True
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "http://localhost:3100"
    """Endereço pelo qual o serviço envia traces e scores."""
    langfuse_public_url: str | None = None
    """Endereço da UI no browser, para os links do console (padrão: `langfuse_base_url`)."""
    langfuse_project_id: str | None = None
    """Id do projeto; se ausente, é descoberto pela API do Langfuse."""
    langfuse_environment: str = "development"
    langfuse_timeout_seconds: int = 20
    """Timeout do exportador de spans. O default do SDK (5s) descarta lotes
    silenciosamente quando o Langfuse está ocupado (ex.: logo após subir)."""

    # Tools — kind="python" (ver agent_service/tools/python_tool.py)
    custom_python_tools_enabled: bool = False
    """Desligado por padrão: tools Python rodam num namespace restrito, mas
    NÃO são uma sandbox forte contra um autor mal-intencionado — só ligue se
    quem tem acesso à API/console já for confiável (o serviço não tem
    autenticação neste MVP)."""


@lru_cache
def get_settings() -> Settings:
    return Settings()
