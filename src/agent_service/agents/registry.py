"""Resolve agentes dinamicamente a partir de `agents/store.py`.

Agentes não são mais um dict hardcoded — qualquer linha em
`agent_definitions` (criada pela API `/agents` ou pela UI) vira um agente
utilizável em `/chat`/`/chat/stream` sem restart. O cache abaixo evita
reconstruir o `Agent` do Agno a cada request; é invalidado comparando
`updated_at`, então uma edição feita pela UI passa a valer na próxima
requisição.
"""

from datetime import datetime
from typing import Any

from agno.agent import Agent

from agent_service.agents.base import build_agent
from agent_service.agents.store import get_definition, list_definitions
from agent_service.tools.store import get_tool as get_tool_row
from agent_service.tools.registry import resolve_tools_with_stamp

_cache: dict[str, tuple[Agent, datetime, tuple[datetime, ...]]] = {}


class UnknownAgentTypeError(ValueError):
    pass


def _build_from_definition(definition: dict[str, Any]) -> tuple[Agent, tuple[datetime, ...]]:
    tools, tools_stamp = resolve_tools_with_stamp(definition["tools"] or [])
    return build_agent(
        agent_id=definition["agent_type"],
        name=definition["name"],
        instructions=definition["instructions"],
        tools=tools,
        model_provider=definition["model_provider"],
        model_id=definition["model_id"],
        model_credential_id=definition.get("model_credential_id"),
        knowledge_collection=definition.get("knowledge_collection"),
        num_history_runs=definition["num_history_runs"],
        memory_backend=definition["memory_backend"],
    ), tools_stamp


def get_agent_with_definition(agent_type: str) -> tuple[Agent, dict[str, Any]]:
    """Como `get_agent`, mas devolve também a definição usada — a observabilidade
    registra em cada trace o nome e a `prompt_version` que responderam."""
    definition = get_definition(agent_type)
    if definition is None:
        raise UnknownAgentTypeError(
            f"Tipo de agente desconhecido: {agent_type!r}. Veja GET /agents para os disponíveis."
        )

    cached = _cache.get(agent_type)
    if cached is not None and cached[1] == definition["updated_at"]:
        # A definição não mudou, mas uma tool dela pode ter mudado: o `Function`
        # com o schema antigo está dentro do `Agent` já construído.
        if cached[2] == _tools_stamp(definition):
            return cached[0], definition

    agent, tools_stamp = _build_from_definition(definition)
    _cache[agent_type] = (agent, definition["updated_at"], tools_stamp)
    return agent, definition


def _tools_stamp(definition: dict[str, Any]) -> tuple[datetime, ...]:
    rows = (get_tool_row(name) for name in definition["tools"] or [])
    return tuple(row["updated_at"] for row in rows if row is not None)


def get_agent(agent_type: str) -> Agent:
    return get_agent_with_definition(agent_type)[0]


def list_agent_types() -> list[str]:
    return [d["agent_type"] for d in list_definitions()]


def all_agents() -> list[Agent]:
    """Snapshot no momento da chamada — usado só pra registrar as rotas
    nativas do AgentOS/playground no startup. Agentes criados depois do
    boot funcionam normalmente via `get_agent` (usado por `/chat`), só não
    aparecem no playground do AgentOS até o próximo restart.
    """
    return [_build_from_definition(d)[0] for d in list_definitions()]
