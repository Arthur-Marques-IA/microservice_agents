"""Resumo incremental da sessão por agente.

`session_summary`: com ele ligado, o que sai da janela de histórico
(`num_history_runs`) entra num resumo que vai no prompt — a conversa longa mantém
o contexto sem reenviar todas as trocas. Ver `memory/managers.py`.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_definitions",
        sa.Column("session_summary", sa.Boolean, nullable=False, server_default=sa.false()),
    )
