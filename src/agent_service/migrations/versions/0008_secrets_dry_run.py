"""Segredos referenciados pelas tools e a declaração de suporte a dry-run.

- `secrets`: valores que uma tool usa por referência (`{{secret:NOME}}`), cifrados com
  a `CREDENTIALS_ENCRYPTION_KEY`, como as chaves de provedor. A definição da tool guarda
  só a referência, então ler a tool (API, CLI, MCP, console) nunca mostra o valor.
- `tool_definitions.dry_run_support`: a API da tool trata o `X-Kuro-Dry-Run`? Num teste,
  uma tool com efeito colateral (ou não classificada) que não declara isto não é chamada.
  `NULL` = não declarado.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "secrets",
        sa.Column("name", sa.String, primary_key=True),
        sa.Column("value_encrypted", sa.Text, nullable=False),
        sa.Column("description", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("tool_definitions", sa.Column("dry_run_support", sa.Boolean, nullable=True))


def downgrade() -> None:
    # batch: o SQLite (o banco dos testes) não remove coluna com ALTER direto.
    with op.batch_alter_table("tool_definitions") as batch:
        batch.drop_column("dry_run_support")
    op.drop_table("secrets")
