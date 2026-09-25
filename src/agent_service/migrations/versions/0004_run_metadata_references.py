"""Correlação das execuções com o sistema que chama, e a decisão de referência.

- `run_metadata`: pares chave/valor que quem chama manda no `/chat`/`/analyze`
  (ex.: `conversation_id`, `lead_id`). Tabela própria, e não uma coluna JSON,
  para o filtro ser indexado e igual no Postgres e no SQLite.
- `run_references`: a decisão que *deveria* ter saído — no modo shadow, a do
  agente legado. É a base da taxa de concordância e do dataset do `kuro eval`.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_metadata",
        sa.Column("run_id", sa.String, primary_key=True),
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("value", sa.String, nullable=False),
    )
    op.create_index("ix_run_metadata_key_value", "run_metadata", ["key", "value"])
    op.create_table(
        "run_references",
        sa.Column("run_id", sa.String, primary_key=True),
        sa.Column("reference", sa.JSON, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
