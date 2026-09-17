"""`dependencies` da requisição em curso, visível para as tools.

Um parâmetro de tool com `source="dependency"` (ver `tools/api_tool.py`) é
preenchido pelo servidor a partir do `dependencies` do `/chat` — não pelo
modelo, que nem chega a ver esse parâmetro no schema. O valor viaja por um
`ContextVar` porque a tool é chamada lá dentro do agent loop do Agno, longe
da requisição: o Agno chama `entrypoint(**argumentos)` sem por onde passar
contexto nosso.

Cada requisição do FastAPI roda na sua própria task, portanto no seu próprio
contexto — um `set` aqui não vaza para outra requisição. Vale também para a
tool executada numa thread (`asyncio.to_thread` copia o contexto).
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_dependencies: ContextVar[dict[str, Any]] = ContextVar("tool_dependencies", default={})


def set_dependencies(dependencies: dict[str, Any] | None) -> None:
    _dependencies.set(dict(dependencies or {}))


def get_dependencies() -> dict[str, Any]:
    return _dependencies.get()


@contextmanager
def dependencies_scope(dependencies: dict[str, Any] | None):
    """Define as dependências só durante o bloco — usado pelo teste de tool
    (`POST /tools/{nome}/invoke`), que não passa por um run de agente."""
    token = _dependencies.set(dict(dependencies or {}))
    try:
        yield
    finally:
        _dependencies.reset(token)
