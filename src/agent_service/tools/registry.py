"""Registro central de tools disponíveis para os agentes.

Definições de agente (`agents/store.py`) guardam tools como `list[str]` de
**nomes**, nunca código executável — `resolve_tools` traduz esses nomes pros
callables reais na hora de montar o `Agent`. Isso é o que permite a UI de
criação de agente oferecer um multi-select de tools sem poder injetar
código arbitrário via API.
"""

from typing import Any, Callable

# MVP: nenhuma tool própria ainda. Tools built-in do Agno (ex. DuckDuckGoTools,
# ReasoningTools) entram aqui conforme os agentes precisarem — a chave é o
# nome estável usado tanto pelo formulário de criação de agente quanto por
# `GET /tools`.
TOOL_REGISTRY: dict[str, Callable[..., Any]] = {}


class UnknownToolError(ValueError):
    pass


def resolve_tools(names: list[str]) -> list[Callable[..., Any]]:
    tools = []
    for name in names:
        try:
            tools.append(TOOL_REGISTRY[name])
        except KeyError as exc:
            raise UnknownToolError(f"Tool desconhecida: {name!r}") from exc
    return tools


def list_available_tools() -> list[str]:
    return sorted(TOOL_REGISTRY.keys())
