"""Num teste (`dry_run`), tool com efeito colateral só é chamada se declara que trata o teste.

O `dry_run` sempre foi um aviso: a chamada leva `X-Kuro-Dry-Run: true` e quem implementa
a API decide o que simular. Uma API que ignora o header grava de verdade — e o teste,
que parecia seguro, criava lead e ficha em produção. Agora o Kuro só chama, num teste,
a tool que:

- não tem efeito colateral (`side_effect=false`), ou
- declara que a API dela trata o header (`dry_run_support=true`) — só `api` e `python`,
  as que mandam o header; uma builtin (o `email`, por exemplo) não tem como tratá-lo.

O resto — com efeito colateral, ou ainda não classificada — não é chamado: o modelo recebe
um texto dizendo que a tool não rodou porque é teste, com os argumentos que ele mandou, e
segue a conversa. Não conta como falha de tool.

Dois pontos de entrada, para cobrir todo caminho:
- o run de um agente: um `tool_hook` do Agno (`guard_hook`), que vê toda chamada de tool,
  inclusive as funções de uma toolkit;
- `tools/invoke.py`: o teste de tool (`tool_invoke`) e a etapa `action` de um procedural,
  que chamam a tool sem passar pelo agente.
"""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from agent_service.tools.context import is_dry_run

SKIPPED_PREFIX = "[teste] Não executada:"


def block_reason(row: dict[str, Any]) -> str | None:
    """Por que a tool não roda num teste, ou `None` se roda."""
    if row.get("side_effect") is False:
        return None
    if row.get("dry_run_support") is True and row.get("kind") in ("api", "python"):
        return None
    if row.get("side_effect") is True:
        return "ela tem efeito colateral e não declara que a API dela trata o teste (X-Kuro-Dry-Run)"
    return "ela ainda não foi classificada (side_effect vazio) e pode ter efeito colateral"


def skipped_message(tool_name: str, reason: str, arguments: dict[str, Any]) -> str:
    """O que volta ao modelo no lugar da resposta da tool. Só os argumentos que o modelo
    mandou: nada de `dependencies`, constantes ou segredos."""
    try:
        args = json.dumps(arguments, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        args = str(arguments)
    return (
        f"{SKIPPED_PREFIX} esta é uma execução de teste (dry_run) e a tool {tool_name!r} não foi chamada, porque "
        f"{reason}. Argumentos que seriam enviados: {args}. Siga a conversa sabendo que nada foi gravado. "
        f"(Para quem opera: se a tool só lê, marque side_effect=false; se a API dela trata o header "
        f"X-Kuro-Dry-Run, marque dry_run_support=true.)"
    )


def is_skipped(result: Any) -> bool:
    return isinstance(result, str) and result.startswith(SKIPPED_PREFIX)


def function_names(row: dict[str, Any], built: Any) -> list[str]:
    """Os nomes com que o Agno chama a tool: o da `Function` (api), o da função (python) e
    os de cada função de uma toolkit (builtin)."""
    functions = getattr(built, "functions", None)
    if isinstance(functions, dict) and functions:
        return list(functions)
    name = getattr(built, "name", None) or getattr(built, "__name__", None)
    return [name] if isinstance(name, str) else [row["tool_name"]]


def guard_hook(blocked: dict[str, tuple[str, str]]) -> Callable[..., Awaitable[Any]]:
    """`tool_hook` do Agno: `blocked` é nome da função → (nome da tool, motivo).

    Assíncrono: o run dos agentes é `arun`, e no caminho assíncrono do Agno um hook
    síncrono devolveria a corrotina da tool sem esperá-la."""

    async def kuro_dry_run_guard(function_name: str, function_call: Callable[..., Any], arguments: dict[str, Any]) -> Any:
        hit = blocked.get(function_name)
        if hit is not None and is_dry_run():
            return skipped_message(hit[0], hit[1], arguments)
        return await function_call(**arguments)

    return kuro_dry_run_guard
