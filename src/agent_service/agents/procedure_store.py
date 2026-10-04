"""Estado das conversas de um agente procedural (`procedure_runs`).

Uma linha por (agente, sessão). Toda gravação confere a `version` lida: se
outra mensagem da mesma sessão gravou no meio do caminho, a escrita falha com
`ProcedureConflictError` em vez de sobrescrever — é isso que impede uma ação
de rodar duas vezes quando duas mensagens chegam juntas.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from agent_service.db import get_db

metadata = MetaData()

procedure_runs = Table(
    "procedure_runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("agent_type", String, nullable=False),
    Column("session_id", String, nullable=False),
    Column("user_id", String, nullable=True),
    # Etapa atual (`None` quando concluído) e status, em colunas para o funil.
    Column("stage", String, nullable=True),
    Column("status", String, nullable=False, default="active"),
    Column("state", JSON, nullable=False),
    # A última resposta do agente: é o que dá sentido a um "sim" ou "é 123".
    Column("last_reply", Text, nullable=True),
    Column("dry_run", Boolean, nullable=False, default=False),
    Column("version", Integer, nullable=False, default=1),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint("agent_type", "session_id", name="uq_procedure_runs_session"),
)


class ProcedureConflictError(RuntimeError):
    """Outra mensagem da mesma sessão gravou o estado antes desta."""


def get_procedure(agent_type: str, session_id: str) -> dict[str, Any] | None:
    with get_db().db_engine.connect() as conn:
        row = conn.execute(
            select(procedure_runs).where(
                procedure_runs.c.agent_type == agent_type, procedure_runs.c.session_id == session_id
            )
        ).first()
    return dict(row._mapping) if row else None


def create_procedure(
    *, agent_type: str, session_id: str, user_id: str | None, state: dict[str, Any], stage: str | None, dry_run: bool
) -> dict[str, Any]:
    row_id = uuid.uuid4().hex
    try:
        with get_db().db_engine.begin() as conn:
            conn.execute(
                insert(procedure_runs).values(
                    id=row_id,
                    agent_type=agent_type,
                    session_id=session_id,
                    user_id=user_id,
                    stage=stage,
                    status="active" if stage is not None else "done",
                    state=state,
                    dry_run=dry_run,
                    version=1,
                )
            )
    except IntegrityError as exc:  # a outra mensagem criou primeiro
        raise ProcedureConflictError(session_id) from exc
    created = get_procedure(agent_type, session_id)
    assert created is not None
    return created


def save_procedure(
    row: dict[str, Any], *, state: dict[str, Any], stage: str | None, last_reply: Any = ...
) -> dict[str, Any]:
    """Grava o estado se ninguém gravou desde que `row` foi lido; devolve a linha nova."""
    values: dict[str, Any] = {
        "state": state,
        "stage": stage,
        "status": "active" if stage is not None else "done",
        "version": row["version"] + 1,
        "updated_at": datetime.now(timezone.utc),
    }
    if last_reply is not ...:
        values["last_reply"] = last_reply
    with get_db().db_engine.begin() as conn:
        result = conn.execute(
            update(procedure_runs)
            .where(procedure_runs.c.id == row["id"], procedure_runs.c.version == row["version"])
            .values(**values)
        )
    if result.rowcount != 1:
        raise ProcedureConflictError(row["session_id"])
    return {**row, **values}


def delete_procedure(agent_type: str, session_id: str) -> bool:
    with get_db().db_engine.begin() as conn:
        result = conn.execute(
            delete(procedure_runs).where(
                procedure_runs.c.agent_type == agent_type, procedure_runs.c.session_id == session_id
            )
        )
    return result.rowcount > 0


def delete_procedures_of(agent_type: str) -> None:
    """Some com o agente: estado de conversa de um agente que não existe mais só
    confundiria um agente novo com o mesmo nome."""
    with get_db().db_engine.begin() as conn:
        conn.execute(delete(procedure_runs).where(procedure_runs.c.agent_type == agent_type))


def funnel(agent_type: str, *, include_dry_run: bool = False) -> list[dict[str, Any]]:
    """Quantas conversas estão em cada etapa — onde as pessoas param."""
    query = (
        select(procedure_runs.c.stage, procedure_runs.c.status, func.count().label("sessions"))
        .where(procedure_runs.c.agent_type == agent_type)
        .group_by(procedure_runs.c.stage, procedure_runs.c.status)
    )
    if not include_dry_run:
        query = query.where(procedure_runs.c.dry_run.is_(False))
    with get_db().db_engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(query).all()]
