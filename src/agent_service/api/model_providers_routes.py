"""Catálogo de provedores de modelo suportados (`/model-providers`) — o que
cada um precisa (chave, base_url) e quantas credenciais já existem, pro
console montar o diálogo de nova chave e agrupar a tela de credenciais por
provedor. CRUD e teste de credenciais em `api/model_credentials_routes.py`.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from agent_service.models import store
from agent_service.models.catalog import PROVIDERS

router = APIRouter(prefix="/model-providers", tags=["model-providers"])


class ModelProviderOut(BaseModel):
    provider: str
    label: str
    requires_api_key: bool
    supports_custom_base_url: bool
    default_model_id: str
    docs_url: str
    credential_count: int
    configured_count: int


@router.get("", response_model=list[ModelProviderOut])
def list_model_providers() -> list[ModelProviderOut]:
    result = []
    for name, spec in PROVIDERS.items():
        credentials = store.list_credentials(name)
        configured_count = sum(1 for c in credentials if c["api_key_encrypted"] or not spec.requires_api_key)
        result.append(
            ModelProviderOut(
                provider=spec.provider,
                label=spec.label,
                requires_api_key=spec.requires_api_key,
                supports_custom_base_url=spec.supports_custom_base_url,
                default_model_id=spec.default_model_id,
                docs_url=spec.docs_url,
                credential_count=len(credentials),
                configured_count=configured_count,
            )
        )
    return result
