"""Persistência das chaves de provedor de modelo — uma tabela (`model_provider_credentials`),
uma linha por provedor. A chave de API nunca é guardada em texto plano: `crypto.py`
cifra antes de `insert`/`update` e decifra só quando `provider.get_model` precisa
montar o cliente do SDK; as respostas da API (`api/model_providers_routes.py`)
nunca devolvem `api_key_encrypted`.

Same shape/estilo de `tools/store.py`: `init_store()` cria a tabela
(`create_all(checkfirst=True)`), sem Alembic.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, MetaData, String, delete, func, insert, select, update
from sqlalchemy import Table as SATable

from agent_service.db import get_db
from agent_service.models.crypto import decrypt_secret, encrypt_secret, mask_secret

metadata = MetaData()

model_provider_credentials = SATable(
    "model_provider_credentials",
    metadata,
    Column("provider", String, primary_key=True),
    Column("api_key_encrypted", String, nullable=True),
    # Só os últimos 4 chars da chave, em texto plano — pra reconhecer qual é sem
    # decifrar a cada listagem. Nunca a chave inteira.
    Column("key_hint", String, nullable=True),
    Column("base_url", String, nullable=True),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("last_tested_at", DateTime(timezone=True), nullable=True),
    Column("last_test_ok", Boolean, nullable=True),
    Column("last_test_message", String, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
)


def init_store() -> None:
    metadata.create_all(get_db().db_engine, checkfirst=True)


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping)


def list_providers() -> list[dict[str, Any]]:
    with get_db().db_engine.connect() as conn:
        rows = conn.execute(select(model_provider_credentials).order_by(model_provider_credentials.c.provider)).all()
        return [_row_to_dict(r) for r in rows]


def get_provider_row(provider: str) -> dict[str, Any] | None:
    with get_db().db_engine.connect() as conn:
        row = conn.execute(
            select(model_provider_credentials).where(model_provider_credentials.c.provider == provider)
        ).first()
        return _row_to_dict(row) if row else None


def get_decrypted_api_key(provider: str) -> str | None:
    """`None` se o provedor não tem linha, não tem chave salva, ou está desabilitado."""
    row = get_provider_row(provider)
    if row is None or not row["enabled"] or not row["api_key_encrypted"]:
        return None
    return decrypt_secret(row["api_key_encrypted"])


def upsert_provider(
    provider: str,
    *,
    api_key: str | None = None,
    clear_api_key: bool = False,
    base_url: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Cria ou atualiza um provedor. `api_key=None` (sem `clear_api_key`) preserva a
    chave já salva — só reenvia quando o admin realmente quer trocá-la."""
    current = get_provider_row(provider)
    engine = get_db().db_engine

    values: dict[str, Any] = {}
    if api_key is not None:
        values["api_key_encrypted"] = encrypt_secret(api_key)
        values["key_hint"] = mask_secret(api_key)
    elif clear_api_key:
        values["api_key_encrypted"] = None
        values["key_hint"] = None
    if base_url is not None:
        values["base_url"] = base_url or None
    if enabled is not None:
        values["enabled"] = enabled

    with engine.begin() as conn:
        if current is None:
            conn.execute(
                insert(model_provider_credentials).values(
                    provider=provider,
                    api_key_encrypted=values.get("api_key_encrypted"),
                    key_hint=values.get("key_hint"),
                    base_url=values.get("base_url"),
                    enabled=values.get("enabled", True),
                )
            )
        elif values:
            conn.execute(
                update(model_provider_credentials)
                .where(model_provider_credentials.c.provider == provider)
                .values(**values)
            )

    updated = get_provider_row(provider)
    assert updated is not None
    return updated


def record_test_result(provider: str, *, ok: bool, message: str | None, tested_at: datetime) -> dict[str, Any] | None:
    engine = get_db().db_engine
    with engine.begin() as conn:
        result = conn.execute(
            update(model_provider_credentials)
            .where(model_provider_credentials.c.provider == provider)
            .values(last_tested_at=tested_at, last_test_ok=ok, last_test_message=message)
        )
        if result.rowcount == 0:
            return None
    return get_provider_row(provider)


def delete_provider(provider: str) -> None:
    engine = get_db().db_engine
    with engine.begin() as conn:
        conn.execute(delete(model_provider_credentials).where(model_provider_credentials.c.provider == provider))
