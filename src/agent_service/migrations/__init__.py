"""Migrações do schema com Alembic — o que substitui `create_all` + `ALTER TABLE` à mão.

`upgrade_database()` roda no startup (`main.py`) e leva o banco até a última
revisão. Não há `alembic.ini`: a configuração é montada aqui, apontando para
`versions/` dentro do pacote, então funciona igual no container e no `uv run`.

As tabelas do Agno (`agno_*`) e as de vetores do pgvector ficam de fora: o
próprio Agno as cria e mantém.

Para uma mudança de schema nova: crie `versions/NNNN_descricao.py` com
`revision`/`down_revision` encadeados e operações explícitas (`op.add_column`,
`op.create_table`...). Nunca importe as tabelas do código da aplicação dentro de
uma migração — elas mudam depois, e a migração precisa descrever o schema
daquele momento.

Para rodar à mão (ex.: antes de subir uma versão nova): `uv run kuro-migrate`.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

from agent_service.db import get_db

logger = logging.getLogger(__name__)

_SCRIPT_LOCATION = Path(__file__).parent


def _config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(_SCRIPT_LOCATION))
    return config


def upgrade_database(engine: Engine | None = None) -> None:
    """Leva o banco até a última revisão. Idempotente: sem revisão nova, não faz nada.

    Um banco anterior ao Alembic (tabelas criadas por `create_all`) passa pela
    revisão de base como qualquer outro: ela cria o que falta e adiciona as
    colunas que faltam, sem recriar nada."""
    engine = engine or get_db().db_engine
    config = _config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def main() -> None:
    """`kuro-migrate`: aplica as migrações pendentes e sai."""
    logging.basicConfig(level=logging.INFO)
    upgrade_database()
    logger.info("Banco na última revisão.")
