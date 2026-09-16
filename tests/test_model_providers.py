"""Testes das chaves de provedor de modelo: cifra em repouso (`crypto.py`),
persistência (`store.py`), resolução em `provider.get_model` e o CRUD/teste
expostos em `api/model_providers_routes.py`.
"""

import dataclasses

import pytest
from fastapi import HTTPException

from agent_service.models import catalog, crypto, store
from agent_service.models.catalog import ProviderProbeError
from agent_service.models.provider import ProviderNotConfiguredError, UnknownModelProviderError, get_model

from agent_service.api.model_providers_routes import (
    ModelProviderTestIn,
    ModelProviderUpdateIn,
    delete_model_provider,
    get_model_provider,
    list_model_providers,
    update_model_provider,
)
from agent_service.api.model_providers_routes import test_model_provider as call_test_model_provider


@pytest.fixture(autouse=True)
def clean_providers():
    for provider in catalog.PROVIDERS:
        store.delete_provider(provider)
    yield
    for provider in catalog.PROVIDERS:
        store.delete_provider(provider)


# -- crypto -----------------------------------------------------------------


def test_encrypt_decrypt_roundtrip():
    token = crypto.encrypt_secret("sk-super-secret-123")
    assert token != "sk-super-secret-123"
    assert crypto.decrypt_secret(token) == "sk-super-secret-123"


def test_mask_secret_keeps_only_last_four_chars():
    assert crypto.mask_secret("sk-abcdefgh1234") == "····1234"
    assert crypto.mask_secret("ab") == "····"


# -- store --------------------------------------------------------------


def test_upsert_creates_and_preserves_key_when_omitted():
    store.upsert_provider("openai", api_key="sk-first-key", base_url=None, enabled=True)
    row = store.get_provider_row("openai")
    assert row["key_hint"] == crypto.mask_secret("sk-first-key")
    assert store.get_decrypted_api_key("openai") == "sk-first-key"

    # Atualiza só `enabled`, sem reenviar a chave: ela continua a mesma.
    store.upsert_provider("openai", enabled=False)
    assert store.get_decrypted_api_key("openai") is None  # desabilitado, não lê a chave
    row = store.get_provider_row("openai")
    assert row["enabled"] is False
    assert row["api_key_encrypted"] is not None  # a chave em si não foi apagada


def test_clear_api_key_removes_it():
    store.upsert_provider("openai", api_key="sk-to-clear", enabled=True)
    store.upsert_provider("openai", clear_api_key=True)
    row = store.get_provider_row("openai")
    assert row["api_key_encrypted"] is None
    assert row["key_hint"] is None


def test_record_test_result_updates_row():
    store.upsert_provider("openai", api_key="sk-x", enabled=True)
    from datetime import UTC, datetime

    updated = store.record_test_result("openai", ok=True, message=None, tested_at=datetime.now(UTC))
    assert updated["last_test_ok"] is True

    assert store.record_test_result("does-not-exist", ok=True, message=None, tested_at=datetime.now(UTC)) is None


# -- provider.get_model ------------------------------------------------------


def test_get_model_google_falls_back_to_settings_env_key():
    model = get_model()
    assert model.provider == "Google"


def test_get_model_unknown_provider_raises():
    with pytest.raises(UnknownModelProviderError):
        get_model(provider="does-not-exist")


def test_get_model_openai_without_stored_key_raises_not_configured():
    with pytest.raises(ProviderNotConfiguredError):
        get_model(provider="openai", model_id="gpt-4.1-mini")


def test_get_model_openai_uses_stored_key():
    store.upsert_provider("openai", api_key="sk-test-key", enabled=True)
    model = get_model(provider="openai", model_id="gpt-4.1-mini")
    assert model.id == "gpt-4.1-mini"


def test_get_model_ollama_needs_no_key():
    model = get_model(provider="ollama", model_id="llama3.1")
    assert model.id == "llama3.1"


# -- routes ---------------------------------------------------------------


def test_list_model_providers_reports_catalog_and_configured_state():
    store.upsert_provider("anthropic", api_key="sk-ant-123456", enabled=True)

    providers = {p.provider: p for p in list_model_providers()}

    assert set(providers) == set(catalog.PROVIDERS)
    assert providers["anthropic"].configured is True
    assert providers["anthropic"].key_hint == "····3456"
    assert providers["openai"].configured is False
    assert providers["ollama"].configured is True  # não exige chave


def test_get_model_provider_unknown_is_404():
    with pytest.raises(HTTPException) as exc:
        get_model_provider("does-not-exist")
    assert exc.value.status_code == 404


def test_update_model_provider_rejects_enabling_without_key():
    with pytest.raises(HTTPException) as exc:
        update_model_provider("openai", ModelProviderUpdateIn(enabled=True))
    assert exc.value.status_code == 422


def test_update_model_provider_rejects_base_url_when_unsupported():
    with pytest.raises(HTTPException) as exc:
        update_model_provider("anthropic", ModelProviderUpdateIn(base_url="http://evil.example"))
    assert exc.value.status_code == 422


def test_update_model_provider_saves_key_and_enables():
    out = update_model_provider("openai", ModelProviderUpdateIn(api_key="sk-live-key", enabled=True))
    assert out.configured is True
    assert out.enabled is True
    assert out.key_hint == "····-key"


def test_delete_model_provider_clears_it():
    store.upsert_provider("openai", api_key="sk-x", enabled=True)
    delete_model_provider("openai")
    assert store.get_provider_row("openai") is None


def test_test_model_provider_requires_key(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        call_test_model_provider("openai", ModelProviderTestIn())
    assert exc.value.status_code == 422


def test_test_model_provider_reports_success_and_records_it(monkeypatch):
    monkeypatch.setitem(
        catalog.PROVIDERS,
        "openai",
        dataclasses.replace(catalog.PROVIDERS["openai"], probe=lambda *, api_key, base_url: None),
    )
    store.upsert_provider("openai", api_key="sk-good", enabled=True)

    result = call_test_model_provider("openai", ModelProviderTestIn())

    assert result.ok is True
    assert store.get_provider_row("openai")["last_test_ok"] is True


def test_test_model_provider_reports_failure_without_saving_the_ad_hoc_key(monkeypatch):
    def fake_probe(*, api_key: str, base_url: str | None) -> None:
        raise ProviderProbeError("chave inválida")

    monkeypatch.setitem(catalog.PROVIDERS, "openai", dataclasses.replace(catalog.PROVIDERS["openai"], probe=fake_probe))

    result = call_test_model_provider("openai", ModelProviderTestIn(api_key="sk-ad-hoc"))

    assert result.ok is False
    assert result.message == "chave inválida"
    assert store.get_provider_row("openai") is None  # testar um valor ad-hoc não grava nada
