"""Agentes procedurais: etapas na definição e o estado de cada conversa.

- `agent_definitions.stages`: as etapas de um agente `kind="procedural"`
  (`agents/procedural.py`); `[]` nos demais.
- `procedure_runs`: em que etapa cada conversa está e o que já foi coletado. É a
  fonte da verdade do fluxo — consultável (o funil por etapa é um `GROUP BY`) e
  independente da sessão do Agno. `version` é a trava otimista: duas mensagens
  da mesma sessão ao mesmo tempo não executam a mesma ação duas vezes.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_definitions",
        sa.Column("stages", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
    )
    op.create_table(
        "procedure_runs",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("agent_type", sa.String, nullable=False),
        sa.Column("session_id", sa.String, nullable=False),
        sa.Column("user_id", sa.String, nullable=True),
        sa.Column("stage", sa.String, nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="active"),
        sa.Column("state", sa.JSON, nullable=False),
        sa.Column("last_reply", sa.Text, nullable=True),
        sa.Column("dry_run", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("agent_type", "session_id", name="uq_procedure_runs_session"),
    )
    op.create_index("ix_procedure_runs_funnel", "procedure_runs", ["agent_type", "status", "stage"])
