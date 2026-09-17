"""Cadastro das collections de documentos.

Antes, `COLLECTION_NAMES` era uma lista fixa no código: criar uma base de
conhecimento nova exigia editar Python e reiniciar. Aqui elas viram linhas em
`document_collections`, no mesmo espírito de `agents/store.py` e
`tools/store.py` — a tabela pgvector de cada uma continua sendo criada pelo
Agno na primeira ingestão (`documents/collections.py`).

Sem Alembic: `init_store()` roda `create_all(checkfirst=True)` no startup.
"""

from typing import Any

from sqlalchemy import Boolean, Column, DateTime, MetaData, String, Table, delete, func, insert, select, update

from agent_service.db import get_db

metadata = MetaData()

document_collections = Table(
    "document_collections",
    metadata,
    Column("name", String, primary_key=True),
    Column("label", String, nullable=False),
    Column("description", String, nullable=True),
    Column("is_seed", Boolean, nullable=False, default=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
)

SEED_COLLECTION = "general"


class CollectionNotFoundError(LookupError):
    pass


def init_store() -> None:
    metadata.create_all(get_db().db_engine, checkfirst=True)


def seed_default_collection() -> None:
    """A collection `general` original, para quem já tinha documentos nela."""
    if get_collection_row(SEED_COLLECTION) is None:
        create_collection(
            name=SEED_COLLECTION, label="Geral", description="Base de conhecimento padrão.", is_seed=True
        )


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping)


def list_collections() -> list[dict[str, Any]]:
    with get_db().db_engine.begin() as conn:
        rows = conn.execute(select(document_collections).order_by(document_collections.c.name)).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_collection_names() -> list[str]:
    return [c["name"] for c in list_collections()]


def get_collection_row(name: str) -> dict[str, Any] | None:
    with get_db().db_engine.begin() as conn:
        row = conn.execute(select(document_collections).where(document_collections.c.name == name)).fetchone()
    return _row_to_dict(row) if row is not None else None


def create_collection(*, name: str, label: str, description: str | None = None, is_seed: bool = False) -> dict[str, Any]:
    with get_db().db_engine.begin() as conn:
        conn.execute(
            insert(document_collections).values(
                name=name, label=label, description=description, is_seed=is_seed
            )
        )
    return get_collection_row(name)  # type: ignore[return-value]


def update_collection(name: str, *, label: str | None = None, description: str | None = None) -> dict[str, Any]:
    values = {k: v for k, v in (("label", label), ("description", description)) if v is not None}
    if values:
        with get_db().db_engine.begin() as conn:
            conn.execute(update(document_collections).where(document_collections.c.name == name).values(**values))
    row = get_collection_row(name)
    if row is None:
        raise CollectionNotFoundError(name)
    return row


def delete_collection(name: str) -> None:
    """Remove só o cadastro — os vetores já ingeridos continuam na tabela
    `knowledge_<name>` do pgvector, que é do Agno."""
    with get_db().db_engine.begin() as conn:
        conn.execute(delete(document_collections).where(document_collections.c.name == name))
