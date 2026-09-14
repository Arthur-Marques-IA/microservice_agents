"""Registro de tipos de agente disponíveis no serviço.

A API e o playground/AgentOS resolvem um agente pelo `agent_type` (string),
sem precisar conhecer a classe/instância concreta por trás. Novos tipos
(orquestrador, analista) entram aqui como mais uma entrada no dicionário.
"""

from functools import lru_cache
from typing import Callable

from agno.agent import Agent

from agent_service.agents.conversational import AGENT_TYPE as CONVERSATIONAL
from agent_service.agents.conversational import create_conversational_agent

_AGENT_FACTORIES: dict[str, Callable[[], Agent]] = {
    CONVERSATIONAL: create_conversational_agent,
}


class UnknownAgentTypeError(ValueError):
    pass


@lru_cache
def get_agent(agent_type: str) -> Agent:
    try:
        factory = _AGENT_FACTORIES[agent_type]
    except KeyError as exc:
        raise UnknownAgentTypeError(
            f"Tipo de agente desconhecido: {agent_type!r}. Disponíveis: {list(_AGENT_FACTORIES)}"
        ) from exc
    return factory()


def list_agent_types() -> list[str]:
    return list(_AGENT_FACTORIES)


def all_agents() -> list[Agent]:
    return [get_agent(agent_type) for agent_type in _AGENT_FACTORIES]
