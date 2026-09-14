"""Configuração comum a todos os tipos de agente.

Cada tipo de agente (conversacional, orquestrador, analista) chama
`build_agent` em vez de instanciar `agno.agent.Agent` diretamente, garantindo
que todos compartilhem a mesma forma de resolver modelo, memória, persistência
e histórico — sem duplicar essa configuração em cada agente.
"""

from typing import Any, Callable, Literal

from agno.agent import Agent

from agent_service.db import get_db
from agent_service.memory.common import CommonMemoryBackend
from agent_service.models.provider import get_model

MemoryBackendName = Literal["common", "mem0"]


def build_agent(
    *,
    agent_id: str,
    name: str,
    instructions: list[str],
    tools: list[Callable[..., Any]] | None = None,
    model_provider: str | None = None,
    model_id: str | None = None,
    num_history_runs: int = 10,
    memory_backend: MemoryBackendName = "common",
) -> Agent:
    memory = CommonMemoryBackend()

    pre_hooks = []
    post_hooks = []
    add_dependencies_to_context = False

    if memory_backend == "mem0":
        from agent_service.memory.mem0_hooks import mem0_post_hook, mem0_pre_hook

        pre_hooks = [mem0_pre_hook]
        post_hooks = [mem0_post_hook]
        add_dependencies_to_context = True
        instructions = [
            *instructions,
            "Se houver memórias em `dependencies.mem0_memories`, use-as para "
            "personalizar sua resposta ao usuário.",
        ]

    return Agent(
        id=agent_id,
        name=name,
        model=get_model(provider=model_provider, model_id=model_id),
        db=get_db(),
        memory_manager=memory.manager,
        instructions=instructions,
        tools=tools or [],
        add_history_to_context=True,
        num_history_runs=num_history_runs,
        add_memories_to_context=True,
        enable_agentic_memory=True,
        pre_hooks=pre_hooks or None,
        post_hooks=post_hooks or None,
        add_dependencies_to_context=add_dependencies_to_context,
        markdown=True,
    )
