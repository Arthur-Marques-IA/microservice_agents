"""CRUD e teste de credenciais de modelo (`/model-credentials`).

Várias chaves por provedor são permitidas. Quem configura o agente define qual
ele usa (`model_credential_id` em `api/agents_routes.py`) — é configuração, o
modelo nunca escolhe; sem definição, `models/provider.py` cai na credencial
habilitada mais antiga do provedor.
As chaves nunca voltam numa resposta: só `configured` (bool) e `key_hint`
(últimos 4 chars). `POST .../test` chama um endpoint de leitura barato do
SDK oficial do provedor (listar modelos) pra validar a chave sem gastar
tokens de geração — ver `models/catalog.py`.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_service.agents.store import list_definitions
from agent_service.models import store
from agent_service.models.catalog import ProviderProbeError, ProviderSpec, get_provider_spec

router = APIRouter(prefix="/model-credentials", tags=["model-credentials"])


class ModelCredentialOut(BaseModel):
    id: str
    provider: str
    provider_label: str
    label: str
    configured: bool
    key_hint: str | None = None
    base_url: str | None = None
    enabled: bool
    last_tested_at: datetime | None = None
    last_test_ok: bool | None = None
    last_test_message: str | None = None
    # Nomes dos agentes que apontam pra esta credencial — pra avisar antes de excluir/desabilitar.
    agents_using: list[str] = []
    created_at: datetime
    updated_at: datetime


class ModelCredentialCreateIn(BaseModel):
    provider: str
    label: str = Field(..., min_length=1, max_length=200)
    api_key: str | None = Field(default=None, min_length=1, max_length=4000)
    base_url: str | None = Field(default=None, max_length=500)
    enabled: bool = True


class ModelCredentialUpdateIn(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    api_key: str | None = Field(default=None, min_length=1, max_length=4000)
    """Omitido: mantém a chave já salva. Enviado: substitui (cifrada antes de salvar)."""
    clear_api_key: bool = False
    """Remove a chave salva — ignorado se `api_key` também vier."""
    base_url: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class ModelCredentialTestIn(BaseModel):
    api_key: str | None = Field(default=None, min_length=1, max_length=4000)
    """Testa este valor em vez do salvo — útil pra validar antes de gravar."""
    base_url: str | None = Field(default=None, max_length=500)


class ModelCredentialAdHocTestIn(ModelCredentialTestIn):
    provider: str


class ModelCredentialTestOut(BaseModel):
    ok: bool
    message: str | None = None
    tested_at: datetime


def _spec_or_404(provider: str) -> ProviderSpec:
    spec = get_provider_spec(provider)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Provedor desconhecido: {provider!r}")
    return spec


def _credential_or_404(credential_id: str) -> dict[str, Any]:
    row = store.get_credential(credential_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Credencial não encontrada")
    return row


def _agents_using(credential_id: str) -> list[str]:
    return [d["name"] for d in list_definitions() if d.get("model_credential_id") == credential_id]


def _to_out(row: dict[str, Any]) -> ModelCredentialOut:
    spec = get_provider_spec(row["provider"])
    return ModelCredentialOut(
        id=row["id"],
        provider=row["provider"],
        provider_label=spec.label if spec else row["provider"],
        label=row["label"],
        configured=bool(row["api_key_encrypted"]) or bool(spec and not spec.requires_api_key),
        key_hint=row["key_hint"],
        base_url=row["base_url"],
        enabled=row["enabled"],
        last_tested_at=row["last_tested_at"],
        last_test_ok=row["last_test_ok"],
        last_test_message=row["last_test_message"],
        agents_using=_agents_using(row["id"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("", response_model=list[ModelCredentialOut])
def list_model_credentials(provider: str | None = None) -> list[ModelCredentialOut]:
    return [_to_out(row) for row in store.list_credentials(provider)]


@router.post("", response_model=ModelCredentialOut, status_code=201)
def create_model_credential(body: ModelCredentialCreateIn) -> ModelCredentialOut:
    spec = _spec_or_404(body.provider)
    if not spec.supports_custom_base_url and body.base_url:
        raise HTTPException(status_code=422, detail=f"{spec.label} não aceita base_url customizada")
    if spec.requires_api_key and body.enabled and not body.api_key:
        raise HTTPException(status_code=422, detail=f"{spec.label} exige uma api_key para ser habilitada")

    row = store.create_credential(
        body.provider, body.label, api_key=body.api_key, base_url=body.base_url, enabled=body.enabled
    )
    return _to_out(row)


@router.put("/{credential_id}", response_model=ModelCredentialOut)
def update_model_credential(credential_id: str, body: ModelCredentialUpdateIn) -> ModelCredentialOut:
    current = _credential_or_404(credential_id)
    spec = _spec_or_404(current["provider"])
    if not spec.supports_custom_base_url and body.base_url:
        raise HTTPException(status_code=422, detail=f"{spec.label} não aceita base_url customizada")

    will_have_key = bool(body.api_key) or (not body.clear_api_key and bool(current["api_key_encrypted"]))
    will_be_enabled = body.enabled if body.enabled is not None else current["enabled"]
    if will_be_enabled and spec.requires_api_key and not will_have_key:
        raise HTTPException(status_code=422, detail=f"{spec.label} exige uma api_key para ser habilitada")

    row = store.update_credential(
        credential_id,
        label=body.label,
        api_key=body.api_key,
        clear_api_key=body.clear_api_key,
        base_url=body.base_url,
        enabled=body.enabled,
    )
    assert row is not None
    return _to_out(row)


@router.delete("/{credential_id}", status_code=204)
def delete_model_credential(credential_id: str) -> None:
    _credential_or_404(credential_id)
    store.delete_credential(credential_id)


@router.post("/test", response_model=ModelCredentialTestOut)
def test_ad_hoc_credential(body: ModelCredentialAdHocTestIn) -> ModelCredentialTestOut:
    """Testa provider+api_key antes de salvar — usado no diálogo de nova chave."""
    spec = _spec_or_404(body.provider)
    if spec.requires_api_key and not body.api_key:
        raise HTTPException(status_code=422, detail=f"{spec.label} exige uma api_key para testar")

    tested_at = datetime.now(UTC)
    try:
        spec.probe(api_key=body.api_key, base_url=body.base_url)
        ok, message = True, None
    except ProviderProbeError as exc:
        ok, message = False, str(exc)[:500]
    return ModelCredentialTestOut(ok=ok, message=message, tested_at=tested_at)


@router.post("/{credential_id}/test", response_model=ModelCredentialTestOut)
def test_model_credential(credential_id: str, body: ModelCredentialTestIn) -> ModelCredentialTestOut:
    current = _credential_or_404(credential_id)
    spec = _spec_or_404(current["provider"])

    api_key = body.api_key or store.get_decrypted_api_key(credential_id)
    base_url = body.base_url if body.base_url is not None else current["base_url"]
    if spec.requires_api_key and not api_key:
        raise HTTPException(status_code=422, detail=f"{spec.label} exige uma api_key para testar")

    tested_at = datetime.now(UTC)
    try:
        spec.probe(api_key=api_key, base_url=base_url)
        ok, message = True, None
    except ProviderProbeError as exc:
        ok, message = False, str(exc)[:500]

    store.record_test_result(credential_id, ok=ok, message=message, tested_at=tested_at)
    return ModelCredentialTestOut(ok=ok, message=message, tested_at=tested_at)
