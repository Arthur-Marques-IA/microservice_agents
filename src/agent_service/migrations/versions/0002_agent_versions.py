"""Versão da configuração inteira do agente, e em qual versão cada run rodou.

`agent_versions` guarda um snapshot imutável de tudo que muda o comportamento
(instructions, modelo, tools e a config delas, schema, collection, nota de
feedback...), identificado pelo hash. `runs.agent_version` liga a execução a ele.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent_type", sa.String, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("config_hash", sa.String, nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("agent_type", "version", name="uq_agent_versions_agent_version"),
        sa.UniqueConstraint("agent_type", "config_hash", name="uq_agent_versions_agent_hash"),
    )
    op.create_index("ix_agent_versions_agent_type", "agent_versions", ["agent_type"])
    op.add_column("runs", sa.Column("agent_version", sa.Integer, nullable=True))
