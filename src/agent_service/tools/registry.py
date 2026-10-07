"""Resolve nomes de tool (guardados em `agent_definitions.tools`) pros objetos
reais que o Agno espera em `Agent(tools=[...])` — instâncias de `Toolkit`,
`Function` ou callables simples.

As definições ficam em `tool_definitions` (`tools/store.py`), criadas pela
API/UI (`api/tools_routes.py`), nunca hardcoded aqui — isso é o que permite
compor tools sem tocar em código: uma toolkit padrão do Agno (`kind=
"builtin"`, catálogo em `tools/catalog.py`), uma chamada de API descrita em
JSON (`kind="api"`, `tools/api_tool.py`) ou uma função Python enviada pelo
usuário (`kind="python"`, `tools/python_tool.py`).

`resolve_tools` cacheia o objeto construído por tool, invalidado comparando
`updated_at` — mesmo padrão de `agents/registry.py` pro `Agent` em si.
"""

from datetime import datetime
from typing import Any

from agent_service.config import get_settings
from agent_service.tools import dry_run, store
from agent_service.tools.api_tool import ApiToolConfigError, build_api_function
from agent_service.tools.catalog import get_builtin_spec
from agent_service.tools.python_tool import PythonToolConfigError, PythonToolDisabledError, compile_python_tool

_cache: dict[str, tuple[Any, datetime]] = {}


class UnknownToolError(ValueError):
    pass


class ToolBuildError(RuntimeError):
    """A tool existe, mas não pôde ser construída (config inválida, dependência
    ausente, kind Python desligado...). Erro do operador, não de quem chama —
    result num 502 nas rotas de agente/chat, não num 422."""


def _build(row: dict[str, Any]) -> Any:
    kind = row["kind"]
    config = row["config"] or {}
    try:
        if kind == "builtin":
            spec = get_builtin_spec(config.get("builtin_id", ""))
            if spec is None:
                raise ToolBuildError(f"Tool {row['tool_name']!r}: builtin_id {config.get('builtin_id')!r} não existe mais no catálogo.")
            return spec.factory(config.get("params", {}), row["tool_name"])
        if kind == "api":
            return build_api_function(tool_name=row["tool_name"], description=row.get("description"), config=config)
        if kind == "python":
            return compile_python_tool(
                tool_name=row["tool_name"], config=config, enabled=get_settings().custom_python_tools_enabled
            )
    except (ApiToolConfigError, PythonToolConfigError) as exc:
        raise ToolBuildError(f"Tool {row['tool_name']!r}: {exc}") from exc
    except PythonToolDisabledError as exc:
        raise ToolBuildError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - ex.: dependência opcional (ddgs) ausente
        raise ToolBuildError(f"Tool {row['tool_name']!r} ({kind}): {exc}") from exc
    raise ToolBuildError(f"Tool {row['tool_name']!r}: kind desconhecido {kind!r}")


def _resolve_row(name: str) -> tuple[Any, dict[str, Any]]:
    row = store.get_tool(name)
    if row is None:
        raise UnknownToolError(f"Tool desconhecida: {name!r}")
    if not row["enabled"]:
        raise ToolBuildError(f"Tool {name!r} está desativada.")

    cached = _cache.get(name)
    if cached is not None and cached[1] == row["updated_at"]:
        return cached[0], row

    built = _build(row)
    _cache[name] = (built, row["updated_at"])
    return built, row


def _resolve_one(name: str) -> tuple[Any, datetime]:
    built, row = _resolve_row(name)
    return built, row["updated_at"]


def resolve_tools(names: list[str]) -> list[Any]:
    return [built for built, _ in (_resolve_one(name) for name in names)]


def resolve_tools_with_stamp(names: list[str]) -> tuple[list[Any], tuple[datetime, ...]]:
    """Como `resolve_tools`, mas devolve também o `updated_at` de cada tool: é o
    que permite ao cache de agentes perceber que uma tool mudou (o schema que o
    modelo vê vive dentro do `Function`, que ficou preso no `Agent` construído)."""
    resolved = [_resolve_one(name) for name in names]
    return [built for built, _ in resolved], tuple(stamp for _, stamp in resolved)


def resolve_for_agent(names: list[str]) -> tuple[list[Any], tuple[datetime, ...], Any]:
    """Como `resolve_tools_with_stamp`, mais o `tool_hook` que barra, num teste, as tools
    que não podem rodar nele (`tools/dry_run.py`); `None` se todas podem. Mudar
    `side_effect` ou `dry_run_support` muda o `updated_at`, então o agente é refeito."""
    resolved = [_resolve_row(name) for name in names]
    blocked: dict[str, tuple[str, str]] = {}
    for built, row in resolved:
        reason = dry_run.block_reason(row)
        if reason is not None:
            for function_name in dry_run.function_names(row, built):
                blocked[function_name] = (row["tool_name"], reason)
    hook = dry_run.guard_hook(blocked) if blocked else None
    return [built for built, _ in resolved], tuple(row["updated_at"] for _, row in resolved), hook


def tool_exists(name: str) -> bool:
    return store.get_tool(name) is not None


def build_fresh(row: dict[str, Any]) -> Any:
    """Constrói sem usar nem alimentar o cache — para a rota de teste
    (`POST /tools/{name}/invoke`), que deve refletir a config mais recente
    mesmo antes dela ser salva num agente."""
    return _build(row)
