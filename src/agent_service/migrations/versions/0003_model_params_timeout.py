"""Parâmetros do modelo e tempo limite por agente.

`model_params`: temperatura, top_p, max_tokens e thinking_budget (Gemini) — o
que antes ficava no padrão do provedor e fazia a decisão variar entre o agente
legado (temperatura 0.3) e o do Kuro. `timeout_seconds`: quanto uma execução
pode levar antes de o Kuro desistir e responder 504, para quem chama cair no
próprio fallback.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_definitions", sa.Column("model_params", sa.JSON, nullable=True))
    op.add_column("agent_definitions", sa.Column("timeout_seconds", sa.Integer, nullable=True))
