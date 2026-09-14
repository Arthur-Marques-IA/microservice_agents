"""Observabilidade via LangSmith.

`configure_tracing()` é chamado uma vez no startup (ver `main.py`) e apenas
exporta as variáveis de ambiente que o SDK do LangSmith já sabe ler
(`LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`). Com isso,
`@traceable` funciona tanto para o agente quanto para qualquer tool chamada
por ele, sem precisar instrumentar cada chamada de modelo manualmente.

Se `settings.langsmith_tracing_enabled` for False (default em dev sem
credenciais), `traceable` vira essencialmente um no-op.
"""

import os
from typing import Any

from agno.agent import Agent
from langsmith import traceable

from agent_service.config import get_settings


def configure_tracing() -> None:
    settings = get_settings()
    if not settings.langsmith_tracing_enabled:
        os.environ["LANGSMITH_TRACING"] = "false"
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key


@traceable(run_type="chain", name="agent.run")
async def traced_agent_run(agent: Agent, *, message: str, user_id: str, session_id: str) -> Any:
    return await agent.arun(message, user_id=user_id, session_id=session_id)
