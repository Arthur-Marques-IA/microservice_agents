"""Configuração comum a todos os tipos de agente.

Cada tipo de agente (conversacional, orquestrador, analista) chama
`build_agent` em vez de instanciar `agno.agent.Agent` diretamente, garantindo
que todos compartilhem a mesma forma de resolver modelo, memória, persistência
e histórico — sem duplicar essa configuração em cada agente.
"""

from typing import Any, Literal

from agno.agent import Agent
from pydantic import BaseModel

from agent_service.db import get_db
from agent_service.documents.collections import get_collection
from agent_service.memory.common import CommonMemoryBackend
from agent_service.models.provider import get_model

MemoryBackendName = Literal["common", "mem0"]
AgentKind = Literal["conversational", "analysis"]


def build_agent(
    *,
    agent_id: str,
    name: str,
    instructions: list[str],
    tools: list[Any] | None = None,  # Toolkit/Function/callable já resolvidos, ver tools/registry.py
    model_provider: str | None = None,
    model_id: str | None = None,
    model_credential_id: str | None = None,
    model_params: dict[str, Any] | None = None,
    knowledge_collection: str | None = None,
    num_history_runs: int = 10,
    memory_backend: MemoryBackendName = "common",
    kind: AgentKind = "conversational",
    output_schema: type[BaseModel] | None = None,
) -> Agent:
    # Agentes "analysis" são one-shot: sem sessão contínua, sem histórico nem
    # memória — só o documento de entrada e o `output_schema` de saída.
    is_analysis = kind == "analysis"
    # Um backend de memória de longo prazo por vez: com "mem0", o Mem0 substitui
    # a memória do Agno (sem memory_manager, sem a tool `update_user_memory` e sem
    # as memórias do Agno no prompt). O histórico da sessão continua valendo.
    use_agno_memory = not is_analysis and memory_backend == "common"
    memory = CommonMemoryBackend() if use_agno_memory else None
    # `search_knowledge=True` dá ao agente uma tool de busca na collection (RAG
    # agêntico): ele decide quando consultar, em vez de injetarmos tudo no prompt.
    knowledge = get_collection(knowledge_collection) if knowledge_collection else None

    pre_hooks = []
    post_hooks = []
    add_dependencies_to_context = False

    if memory_backend == "mem0" and not is_analysis:
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
        model=get_model(
            provider=model_provider, model_id=model_id, credential_id=model_credential_id, params=model_params
        ),
        # Sem `db` em analysis: ele é one-shot e cada chamada criaria uma linha de
        # sessão `analyze-<uuid>` no Postgres, com o documento inteiro dentro, que
        # ninguém lê depois — o trace já registra tudo. O Agno guarda todo acesso a
        # sessão com `if agent.db is not None`, e a busca na collection não usa
        # `agent.db` (a collection tem a própria), então o RAG continua valendo.
        db=None if is_analysis else get_db(),
        memory_manager=memory.manager if memory else None,
        knowledge=knowledge,
        search_knowledge=knowledge is not None,
        instructions=instructions,
        tools=tools or [],
        add_history_to_context=not is_analysis,
        num_history_runs=num_history_runs,
        add_memories_to_context=use_agno_memory,
        enable_agentic_memory=use_agno_memory,
        pre_hooks=pre_hooks or None,
        post_hooks=post_hooks or None,
        add_dependencies_to_context=add_dependencies_to_context,
        output_schema=output_schema,
        markdown=output_schema is None,
    )
