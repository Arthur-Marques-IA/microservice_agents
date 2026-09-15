"""Persistência das definições de agente e do histórico de versões de prompt.

Duas tabelas próprias do projeto (fora do namespace `agno_*` que o
`PostgresDb` já cria sozinho), no mesmo Postgres:

- `agent_definitions`: o estado atual de cada agente — o que roda em
  runtime. `agents/registry.py` lê daqui pra montar o `Agent` do Agno.
- `agent_prompt_versions`: histórico append-only, só pra auditoria/leitura
  na UI. Nunca é lido em runtime — só a versão "atual" em `agent_definitions`
  importa pra construir o agente.

Sem Alembic/migração: `init_store()` roda `create_all(checkfirst=True)` no
startup, no mesmo espírito do `PostgresDb(create_schema=True)` do Agno.
"""

from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    delete,
    func,
    insert,
    select,
    update,
)

from agent_service.db import get_db

metadata = MetaData()

agent_definitions = Table(
    "agent_definitions",
    metadata,
    Column("agent_type", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("instructions", JSON, nullable=False),
    Column("tools", JSON, nullable=False, default=list),
    Column("model_provider", String, nullable=True),
    Column("model_id", String, nullable=True),
    Column("memory_backend", String, nullable=False, default="common"),
    Column("num_history_runs", Integer, nullable=False, default=10),
    Column("is_seed", Boolean, nullable=False, default=False),
    Column("prompt_version", Integer, nullable=False, default=1),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
)

agent_prompt_versions = Table(
    "agent_prompt_versions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent_type", String, nullable=False, index=True),
    Column("version", Integer, nullable=False),
    Column("instructions", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)


def init_store() -> None:
    metadata.create_all(get_db().db_engine, checkfirst=True)


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping)


def list_definitions() -> list[dict[str, Any]]:
    with get_db().db_engine.connect() as conn:
        rows = conn.execute(select(agent_definitions).order_by(agent_definitions.c.agent_type)).all()
        return [_row_to_dict(r) for r in rows]


def get_definition(agent_type: str) -> dict[str, Any] | None:
    with get_db().db_engine.connect() as conn:
        row = conn.execute(
            select(agent_definitions).where(agent_definitions.c.agent_type == agent_type)
        ).first()
        return _row_to_dict(row) if row else None


def create_definition(
    *,
    agent_type: str,
    name: str,
    instructions: list[str],
    tools: list[str] | None = None,
    model_provider: str | None = None,
    model_id: str | None = None,
    memory_backend: str = "common",
    num_history_runs: int = 10,
    is_seed: bool = False,
) -> dict[str, Any]:
    engine = get_db().db_engine
    with engine.begin() as conn:
        conn.execute(
            insert(agent_definitions).values(
                agent_type=agent_type,
                name=name,
                instructions=instructions,
                tools=tools or [],
                model_provider=model_provider,
                model_id=model_id,
                memory_backend=memory_backend,
                num_history_runs=num_history_runs,
                is_seed=is_seed,
                prompt_version=1,
            )
        )
        conn.execute(
            insert(agent_prompt_versions).values(
                agent_type=agent_type, version=1, instructions=instructions
            )
        )
    definition = get_definition(agent_type)
    assert definition is not None
    return definition


def create_definition_if_missing(**kwargs: Any) -> dict[str, Any] | None:
    """Usado pelo seed: não faz nada se `agent_type` já existir."""
    existing = get_definition(kwargs["agent_type"])
    if existing is not None:
        return None
    return create_definition(**kwargs)


class DefinitionNotFoundError(ValueError):
    pass


def update_definition(
    agent_type: str,
    *,
    name: str | None = None,
    instructions: list[str] | None = None,
    tools: list[str] | None = None,
    model_provider: str | None = None,
    model_id: str | None = None,
    memory_backend: str | None = None,
    num_history_runs: int | None = None,
) -> dict[str, Any]:
    current = get_definition(agent_type)
    if current is None:
        raise DefinitionNotFoundError(agent_type)

    values: dict[str, Any] = {}
    if name is not None:
        values["name"] = name
    if tools is not None:
        values["tools"] = tools
    if model_provider is not None:
        values["model_provider"] = model_provider
    if model_id is not None:
        values["model_id"] = model_id
    if memory_backend is not None:
        values["memory_backend"] = memory_backend
    if num_history_runs is not None:
        values["num_history_runs"] = num_history_runs

    prompt_changed = instructions is not None and instructions != current["instructions"]
    if prompt_changed:
        values["instructions"] = instructions
        values["prompt_version"] = current["prompt_version"] + 1

    engine = get_db().db_engine
    with engine.begin() as conn:
        if values:
            conn.execute(
                update(agent_definitions)
                .where(agent_definitions.c.agent_type == agent_type)
                .values(**values)
            )
        if prompt_changed:
            conn.execute(
                insert(agent_prompt_versions).values(
                    agent_type=agent_type,
                    version=values["prompt_version"],
                    instructions=instructions,
                )
            )

    updated = get_definition(agent_type)
    assert updated is not None
    return updated


def delete_definition(agent_type: str) -> None:
    engine = get_db().db_engine
    with engine.begin() as conn:
        conn.execute(delete(agent_definitions).where(agent_definitions.c.agent_type == agent_type))
        conn.execute(delete(agent_prompt_versions).where(agent_prompt_versions.c.agent_type == agent_type))


def list_prompt_versions(agent_type: str) -> list[dict[str, Any]]:
    with get_db().db_engine.connect() as conn:
        rows = conn.execute(
            select(agent_prompt_versions)
            .where(agent_prompt_versions.c.agent_type == agent_type)
            .order_by(agent_prompt_versions.c.version.desc())
        ).all()
        return [_row_to_dict(r) for r in rows]
