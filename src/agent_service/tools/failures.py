"""Falha de tool: o que conta, de que tipo foi, e a complexidade de um run.

Uma tool `kind="api"` devolve o erro ao modelo como texto ("HTTP 500: ...") — é
o certo, ele pode reagir. Mas para o Agno a chamada deu certo, então o trace
gravava a falha como sucesso. Aqui a tool registra a falha onde ela sabe o que
aconteceu (o status HTTP), e o trace (`observability/tracing.py`) consulta este
registro ao montar a span da tool.

O registro é por run: um `ContextVar` com um dicionário novo a cada execução,
preenchido de dentro da tool e lido pelo trace no mesmo contexto. A chave é o
nome da tool mais o texto exato devolvido, que é o que a span recebe.

O `status` do run não muda: um run com tool que falhou continua `success` se o
agente respondeu. A falha aparece na span (`level=ERROR`, `metadata.failure`) e
na contagem `tool_failures` do run.
"""

from contextvars import ContextVar
from typing import Literal

FailureKind = Literal["invalid_arguments", "not_found", "auth", "unavailable", "config", "exception"]
"""
- `invalid_arguments`: o modelo chamou com argumento faltando ou inválido (4xx) — ajuste o prompt ou o schema;
- `not_found`: 404 — pode ser resposta normal ("não há sessões anteriores"), por isso fica à parte;
- `auth`: 401/403 — configuração da tool (credencial);
- `unavailable`: 5xx, 429, rede ou timeout — o sistema chamado está com problema;
- `config`: destino recusado pela trava de egress (`TOOL_EGRESS_ALLOWLIST`) ou dependency
  que a requisição não mandou — configuração do Kuro ou de quem integra;
- `exception`: o código da tool levantou erro (tools python e builtin).
"""

FAILURE_KINDS: tuple[str, ...] = ("invalid_arguments", "not_found", "auth", "unavailable", "config", "exception")

INTERNAL_TOOLS = frozenset({"update_user_memory", "search_knowledge_base"})
"""Tools que o próprio Agno dá ao agente (memória, busca na base): não decidem
nada do negócio, então não contam para a complexidade."""

_failures: ContextVar[dict[tuple[str, str], tuple[str, int | None]] | None] = ContextVar("tool_failures", default=None)


def classify_http(status_code: int) -> FailureKind | None:
    """`None` = sucesso (2xx/3xx)."""
    if status_code < 400:
        return None
    if status_code in (401, 403):
        return "auth"
    if status_code == 404:
        return "not_found"
    if status_code == 429 or status_code >= 500:
        return "unavailable"
    return "invalid_arguments"


def start_run() -> None:
    """Registro novo para o run que começa (e para cada `tools invoke`)."""
    _failures.set({})


def record_failure(tool_name: str, output: str, kind: FailureKind, http_status: int | None = None) -> None:
    registry = _failures.get()
    if registry is not None:
        registry[(tool_name, output)] = (kind, http_status)


def lookup_failure(tool_name: str, output: object) -> tuple[str, int | None] | None:
    registry = _failures.get()
    if not registry or not isinstance(output, str):
        return None
    return registry.get((tool_name, output))


def complexity(tool_names: list[str]) -> int:
    """1 = nenhuma tool de negócio; 2 = uma ou duas distintas; 3 = três ou mais.
    Distintas porque chamar a mesma tool de novo não torna o run mais complexo."""
    distinct = {name for name in tool_names if name not in INTERNAL_TOOLS}
    if not distinct:
        return 1
    return 2 if len(distinct) <= 2 else 3
