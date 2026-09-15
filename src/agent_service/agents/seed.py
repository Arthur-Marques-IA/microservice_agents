"""Semeia o agente `conversational` original como uma linha em `agent_definitions`.

Chamado uma vez no startup (`main.py`), depois de `store.init_store()`. Não
faz nada se a linha já existir — assim o prompt pode ser editado pela UI sem
ser resetado a cada boot.
"""

from agent_service.agents.conversational import AGENT_TYPE, INSTRUCTIONS
from agent_service.agents.store import create_definition_if_missing


def seed_default_agents() -> None:
    create_definition_if_missing(
        agent_type=AGENT_TYPE,
        name="Agente Conversacional",
        instructions=INSTRUCTIONS,
        tools=[],
        memory_backend="common",
        is_seed=True,
    )
