"""Segredos que as tools usam por referência: `{{secret:NOME}}`.

Um token na definição da tool aparece em toda leitura dela — no `tool_get` do MCP ele
entrava na conversa do modelo, e para trocá-lo alguém precisava digitá-lo de novo no
`tool_apply`. Com a referência, a tool guarda só o nome; o valor é cadastrado uma vez
por quem opera (`kuro secrets set`, que lê do ambiente ou do stdin, nunca da linha de
comando) e fica cifrado com a `CREDENTIALS_ENCRYPTION_KEY`, como as chaves de provedor.
O MCP só lista os nomes: nenhuma tool dele lê ou grava valor.

A referência vale nos headers, no `auth` (token, value, password) e nos parâmetros
`source="const"` de uma tool `kind="api"`, e é resolvida **a cada chamada**: trocar o
valor vale na próxima chamada, sem mexer na tool (o cache das tools é invalidado pelo
`updated_at` da tool, não do segredo). Numa tool `kind="python"`, `secret("NOME")`.
"""

import re
from typing import Any

from sqlalchemy import Column, DateTime, MetaData, String, Text, delete, func, insert, select, update
from sqlalchemy import Table as SATable

from agent_service.db import get_db
from agent_service.models.crypto import decrypt_secret, encrypt_secret, mask_secret

metadata = MetaData()

secrets_table = SATable(
    "secrets",
    metadata,
    Column("name", String, primary_key=True),
    Column("value_encrypted", Text, nullable=False),
    Column("description", String, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
)

NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
REFERENCE_RE = re.compile(r"\{\{\s*secret:([A-Za-z0-9_]+)\s*\}\}")


class SecretError(ValueError):
    """Referência a um segredo que não existe (ou nome inválido)."""


def valid_name(name: str) -> bool:
    return bool(NAME_RE.match(name))


def references(value: Any) -> set[str]:
    """Nomes referenciados em qualquer string dentro de `value` (dict, lista, texto)."""
    if isinstance(value, str):
        return set(REFERENCE_RE.findall(value))
    if isinstance(value, dict):
        return set().union(*(references(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(references(v) for v in value)) if value else set()
    return set()


def list_secrets() -> list[dict[str, Any]]:
    """Nome, descrição e datas — o valor nunca, nem mascarado (os 4 últimos caracteres de
    um token curto já ajudariam a adivinhá-lo)."""
    with get_db().db_engine.connect() as conn:
        rows = conn.execute(
            select(secrets_table.c.name, secrets_table.c.description, secrets_table.c.created_at, secrets_table.c.updated_at)
            .order_by(secrets_table.c.name)
        ).all()
    return [dict(r._mapping) for r in rows]


def exists(name: str) -> bool:
    with get_db().db_engine.connect() as conn:
        return conn.execute(select(secrets_table.c.name).where(secrets_table.c.name == name)).first() is not None


def set_secret(name: str, value: str, description: str | None = None) -> dict[str, Any]:
    if not valid_name(name):
        raise SecretError(f"nome inválido: {name!r} (letras maiúsculas, números e _, começando por letra)")
    if not value:
        raise SecretError("o valor do segredo está vazio")
    encrypted = encrypt_secret(value)  # sem a chave de cifra: EncryptionNotConfiguredError → 503
    engine = get_db().db_engine
    with engine.begin() as conn:
        if conn.execute(select(secrets_table.c.name).where(secrets_table.c.name == name)).first():
            values: dict[str, Any] = {"value_encrypted": encrypted}
            if description is not None:
                values["description"] = description
            conn.execute(update(secrets_table).where(secrets_table.c.name == name).values(**values))
            created = False
        else:
            conn.execute(insert(secrets_table).values(name=name, value_encrypted=encrypted, description=description))
            created = True
    return {"name": name, "created": created, "hint": mask_secret(value)}


def delete_secret(name: str) -> bool:
    engine = get_db().db_engine
    with engine.begin() as conn:
        return conn.execute(delete(secrets_table).where(secrets_table.c.name == name)).rowcount > 0


def get_value(name: str) -> str:
    with get_db().db_engine.connect() as conn:
        row = conn.execute(select(secrets_table.c.value_encrypted).where(secrets_table.c.name == name)).first()
    if row is None:
        raise SecretError(f"o segredo {name!r} não existe — cadastre com `kuro secrets set {name}`")
    return decrypt_secret(row[0])


def resolve(value: Any, found: dict[str, str] | None = None) -> Any:
    """`value` com cada `{{secret:NOME}}` trocado pelo valor. `found` (opcional) recebe os
    valores usados, para quem chamou tirá-los do que volta ao modelo."""
    if isinstance(value, str):
        def swap(match: re.Match[str]) -> str:
            secret = get_value(match.group(1))
            if found is not None:
                found[match.group(1)] = secret
            return secret

        return REFERENCE_RE.sub(swap, value)
    if isinstance(value, dict):
        return {k: resolve(v, found) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, found) for v in value]
    return value


def redact(text: str, values: Any) -> str:
    """Tira os valores dos segredos de um texto que vai ao modelo ou ao trace: muita API
    devolve os headers recebidos no corpo, e um erro do httpx pode trazer a URL inteira."""
    for value in sorted({v for v in values if v and len(v) >= 4}, key=len, reverse=True):
        text = text.replace(value, "{{secret}}")
    return text
