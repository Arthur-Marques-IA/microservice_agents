"""Que valores de uma tool `kind="api"` são segredo.

O `auth` sempre foi mascarado, mas um token também chega por um header comum
(`X-Regente-Token`) ou por um parâmetro fixo (`api_key` na query) — e esses saíam em
texto puro em toda leitura da tool, inclusive no `tool_get` do MCP, direto para a
conversa do modelo. Aqui fica a regra única de "parece segredo", usada para mascarar
na leitura (`api/tools_routes.py`) e para tirar os valores do que volta ao modelo
(`tools/api_tool.py`).

O nome decide, não o valor: o valor não dá para julgar (um token é só texto), e errar
para o lado de mascarar demais custa pouco — quem precisa do valor de verdade usa uma
referência a segredo (`tools/secrets.py`), que não é mascarada porque não é o valor.
"""

import re
from typing import Any

SECRET_MASK = "••••••••"

_SENSITIVE = re.compile(
    r"token|secret|passw|pwd|authorization|cookie|signature|credential|session|bearer"
    r"|api[-_]?key|apikey|access[-_]?key|private[-_]?key|client[-_]?key|(^|[-_])key$",
    re.IGNORECASE,
)


def is_sensitive(name: Any) -> bool:
    return isinstance(name, str) and bool(_SENSITIVE.search(name))


AUTH_SECRET_FIELDS = ("token", "value", "password")


def sensitive_slots(config: dict[str, Any]) -> list[tuple[str, ...]]:
    """Os caminhos (`("headers", "X-Token")`, `("auth", "token")`, `("parameters", 2, "value")`)
    que guardam segredo numa config `kind="api"`."""
    slots: list[tuple[Any, ...]] = []
    for field in AUTH_SECRET_FIELDS:
        if (config.get("auth") or {}).get(field):
            slots.append(("auth", field))
    for name in config.get("headers") or {}:
        if is_sensitive(name):
            slots.append(("headers", name))
    for index, param in enumerate(config.get("parameters") or []):
        if param.get("source") == "const" and is_sensitive(param.get("name")) and "value" in param:
            slots.append(("parameters", index, "value"))
    return slots


def get_slot(config: dict[str, Any], slot: tuple[Any, ...]) -> Any:
    node: Any = config
    for key in slot:
        node = node[key]
    return node


def set_slot(config: dict[str, Any], slot: tuple[Any, ...], value: Any) -> None:
    node: Any = config
    for key in slot[:-1]:
        node = node[key]
    node[slot[-1]] = value
