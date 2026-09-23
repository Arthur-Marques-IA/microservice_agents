"""Resolve agentes dinamicamente a partir de `agents/store.py`.

Agentes não são mais um dict hardcoded — qualquer linha em
`agent_definitions` (criada pela API `/agents` ou pela UI) vira um agente
utilizável em `/chat`/`/chat/stream` sem restart. O cache abaixo evita
reconstruir o `Agent` do Agno a cada request; é invalidado comparando
`updated_at`, então uma edição feita pela UI passa a valer na próxima
requisição.
"""

import logging
from datetime import datetime
from typing import Any

from agno.agent import Agent

from agent_service.agents.base import build_agent
from agent_service.agents.response_model import build_response_model
from agent_service.agents.store import get_definition, get_feedback_note, list_definitions
from agent_service.documents.collections import EmbedderError
from agent_service.tools.store import get_tool as get_tool_row
from agent_service.tools.registry import resolve_tools_with_stamp

# (agent, definition.updated_at, tools_stamp, feedback_note.updated_at)
_CacheEntry = tuple[Agent, datetime, tuple[datetime, ...], datetime | None]
_cache: dict[str, _CacheEntry] = {}

_FEEDBACK_HEADER = "Ajustes aprendidos com feedback de conversas anteriores:\n"


logger = logging.getLogger(__name__)


class UnknownAgentTypeError(ValueError):
    pass


def _build_from_definition(definition: dict[str, Any]) -> tuple[Agent, tuple[datetime, ...]]:
    tools, tools_stamp = resolve_tools_with_stamp(definition["tools"] or [])
    kind = definition.get("kind") or "conversational"
    instructions = definition["instructions"]
    output_schema = None
    if kind == "analysis":
        output_schema = build_response_model(definition["agent_type"], definition.get("response_schema") or [])
    else:
        note = get_feedback_note(definition["agent_type"])
        if note and note["content"]:
            instructions = [*instructions, _FEEDBACK_HEADER + note["content"]]
    return build_agent(
        agent_id=definition["agent_type"],
        name=definition["name"],
        instructions=instructions,
        tools=tools,
        model_provider=definition["model_provider"],
        model_id=definition["model_id"],
        model_credential_id=definition.get("model_credential_id"),
        knowledge_collection=definition.get("knowledge_collection"),
        num_history_runs=definition["num_history_runs"],
        memory_backend=definition["memory_backend"],
        kind=kind,
        output_schema=output_schema,
    ), tools_stamp


def _feedback_stamp(definition: dict[str, Any]) -> datetime | None:
    if (definition.get("kind") or "conversational") != "conversational":
        return None
    note = get_feedback_note(definition["agent_type"])
    return note["updated_at"] if note else None


def get_agent_with_definition(agent_type: str) -> tuple[Agent, dict[str, Any]]:
    """Como `get_agent`, mas devolve também a definição usada — a observabilidade
    registra em cada trace o nome e a `prompt_version` que responderam."""
    definition = get_definition(agent_type)
    if definition is None:
        raise UnknownAgentTypeError(
            f"Tipo de agente desconhecido: {agent_type!r}. Veja GET /agents para os disponíveis."
        )

    cached = _cache.get(agent_type)
    if cached is not None and cached[1] == definition["updated_at"] and cached[3] == _feedback_stamp(definition):
        # A definição não mudou, mas uma tool dela pode ter mudado: o `Function`
        # com o schema antigo está dentro do `Agent` já construído.
        if cached[2] == _tools_stamp(definition):
            return cached[0], definition

    agent, tools_stamp = _build_from_definition(definition)
    _cache[agent_type] = (agent, definition["updated_at"], tools_stamp, _feedback_stamp(definition))
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
    montados = []
    for d in list_definitions():
        try:
            montados.append(_build_from_definition(d)[0])
        except EmbedderError:
            # Um agente apontando para uma collection cujo embedder perdeu a
            # credencial não pode impedir o serviço de subir: os outros sobem, e
            # quem chamar este recebe 502 com o motivo (`api/routes.py`).
            logger.warning(
                "Agente %r ficou fora do AgentOS: embedder da collection não configurado",
                d["agent_type"],
                exc_info=True,
            )
    return montados
