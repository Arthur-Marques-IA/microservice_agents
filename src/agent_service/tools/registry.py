"""Registro central de tools disponíveis para os agentes.

Cada tipo de agente (conversacional, orquestrador, analista) pede um subconjunto
de tools por nome via `get_tools`, em vez de importar/instanciar tools
diretamente — isso mantém `agents/*.py` desacoplado de como cada tool é
implementada ou configurada.
"""

from typing import Any, Callable

# MVP: nenhuma tool própria ainda. Tools built-in do Agno (ex. DuckDuckGoTools,
# ReasoningTools) podem ser adicionadas aqui conforme os agentes precisarem.
TOOL_SETS: dict[str, list[Callable[..., Any]]] = {
    "conversational": [],
}


def get_tools(agent_type: str) -> list[Callable[..., Any]]:
    return TOOL_SETS.get(agent_type, [])
