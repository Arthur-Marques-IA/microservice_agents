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
from typing import Any, AsyncIterator

from agno.agent import Agent
from agno.run.agent import RunOutputEvent
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
async def traced_agent_run(
    agent: Agent,
    *,
    message: str,
    user_id: str,
    session_id: str,
    dependencies: dict[str, Any] | None = None,
) -> Any:
    return await agent.arun(
        message,
        user_id=user_id,
        session_id=session_id,
        dependencies=dependencies,
        add_dependencies_to_context=True if dependencies else None,
    )


@traceable(run_type="chain", name="agent.run_stream")
async def traced_agent_stream(
    agent: Agent,
    *,
    message: str,
    user_id: str,
    session_id: str,
    dependencies: dict[str, Any] | None = None,
) -> AsyncIterator[RunOutputEvent]:
    """Versão em streaming de `traced_agent_run`.

    Precisa ser um generator próprio (não dá pra `@traceable` o handler da
    rota direto: `EventSourceResponse` retorna antes do primeiro token, o
    que fecharia o span cedo demais). `@traceable` sabe lidar com generators
    async nativamente — o span cobre do primeiro ao último evento.
    """
    async for event in agent.arun(
        message,
        user_id=user_id,
        session_id=session_id,
        stream=True,
        stream_events=True,
        dependencies=dependencies,
        add_dependencies_to_context=True if dependencies else None,
    ):
        yield event
