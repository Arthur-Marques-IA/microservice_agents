"""Cadastro e teste de chaves de provedor de modelo (`/model-providers`).

As chaves nunca voltam numa resposta: só `configured` (bool) e `key_hint`
(últimos 4 chars). `POST .../test` chama um endpoint de leitura barato do SDK
oficial do provedor (listar modelos) pra validar a chave sem gastar tokens de
geração — ver `models/catalog.py`.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_service.models import store
from agent_service.models.catalog import PROVIDERS, ProviderProbeError, ProviderSpec, get_provider_spec

router = APIRouter(prefix="/model-providers", tags=["model-providers"])


class ModelProviderOut(BaseModel):
    provider: str
    label: str
    requires_api_key: bool
    supports_custom_base_url: bool
    default_model_id: str
    docs_url: str
    configured: bool
    key_hint: str | None = None
    base_url: str | None = None
    enabled: bool = False
    last_tested_at: datetime | None = None
    last_test_ok: bool | None = None
    last_test_message: str | None = None


class ModelProviderUpdateIn(BaseModel):
    api_key: str | None = Field(default=None, min_length=1, max_length=4000)
    """Omitido: mantém a chave já salva. Enviado: substitui (cifrada antes de salvar)."""
    clear_api_key: bool = False
    """Remove a chave salva — ignorado se `api_key` também vier."""
    base_url: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class ModelProviderTestIn(BaseModel):
    api_key: str | None = Field(default=None, min_length=1, max_length=4000)
    """Testa este valor em vez do salvo — útil pra validar antes de gravar."""
    base_url: str | None = Field(default=None, max_length=500)


class ModelProviderTestOut(BaseModel):
    provider: str
    ok: bool
    message: str | None = None
    tested_at: datetime


def _spec_or_404(provider: str) -> ProviderSpec:
    spec = get_provider_spec(provider)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Provedor desconhecido: {provider!r}")
    return spec


def _to_out(spec: ProviderSpec, row: dict[str, Any] | None) -> ModelProviderOut:
    return ModelProviderOut(
        provider=spec.provider,
        label=spec.label,
        requires_api_key=spec.requires_api_key,
        supports_custom_base_url=spec.supports_custom_base_url,
        default_model_id=spec.default_model_id,
        docs_url=spec.docs_url,
        configured=bool(row and row["api_key_encrypted"]) or not spec.requires_api_key,
        key_hint=row["key_hint"] if row else None,
        base_url=row["base_url"] if row else None,
        enabled=bool(row["enabled"]) if row else False,
        last_tested_at=row["last_tested_at"] if row else None,
        last_test_ok=row["last_test_ok"] if row else None,
        last_test_message=row["last_test_message"] if row else None,
    )


@router.get("", response_model=list[ModelProviderOut])
def list_model_providers() -> list[ModelProviderOut]:
    rows = {row["provider"]: row for row in store.list_providers()}
    return [_to_out(spec, rows.get(name)) for name, spec in PROVIDERS.items()]


@router.get("/{provider}", response_model=ModelProviderOut)
def get_model_provider(provider: str) -> ModelProviderOut:
    spec = _spec_or_404(provider)
    return _to_out(spec, store.get_provider_row(provider))


@router.put("/{provider}", response_model=ModelProviderOut)
def update_model_provider(provider: str, body: ModelProviderUpdateIn) -> ModelProviderOut:
    spec = _spec_or_404(provider)
    if not spec.supports_custom_base_url and body.base_url:
        raise HTTPException(status_code=422, detail=f"{spec.label} não aceita base_url customizada")

    will_have_key = bool(body.api_key) or (
        not body.clear_api_key and bool((store.get_provider_row(provider) or {}).get("api_key_encrypted"))
    )
    if body.enabled and spec.requires_api_key and not will_have_key:
        raise HTTPException(status_code=422, detail=f"{spec.label} exige uma api_key para ser habilitado")

    row = store.upsert_provider(
        provider,
        api_key=body.api_key,
        clear_api_key=body.clear_api_key,
        base_url=body.base_url,
        enabled=body.enabled,
    )
    return _to_out(spec, row)


@router.delete("/{provider}", status_code=204)
def delete_model_provider(provider: str) -> None:
    _spec_or_404(provider)
    store.delete_provider(provider)


@router.post("/{provider}/test", response_model=ModelProviderTestOut)
def test_model_provider(provider: str, body: ModelProviderTestIn) -> ModelProviderTestOut:
    spec = _spec_or_404(provider)

    api_key = body.api_key or store.get_decrypted_api_key(provider)
    base_url = body.base_url if body.base_url is not None else (store.get_provider_row(provider) or {}).get("base_url")
    if spec.requires_api_key and not api_key:
        raise HTTPException(status_code=422, detail=f"{spec.label} exige uma api_key para testar")

    tested_at = datetime.now(UTC)
    try:
        spec.probe(api_key=api_key, base_url=base_url)
        ok, message = True, None
    except ProviderProbeError as exc:
        ok, message = False, str(exc)[:500]

    store.record_test_result(provider, ok=ok, message=message, tested_at=tested_at)
    return ModelProviderTestOut(provider=provider, ok=ok, message=message, tested_at=tested_at)
