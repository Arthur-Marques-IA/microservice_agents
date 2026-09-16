"""Abstração de gerenciamento de modelos.

Isola o resto do serviço de qual SDK/provedor de LLM está por trás de um
agente. As chaves de API vêm de `models/store.py` (cifradas em repouso,
cadastradas pelo console em `/model-providers`); `google` também aceita o
fallback antigo via `GOOGLE_API_KEY` no ambiente, para não quebrar quem já
rodava assim antes da UI de chaves existir.

Novo provedor: um branch aqui + uma entrada em `models/catalog.py` (pro
console saber pedir a chave certa e validar).
"""

from agno.models.base import Model

from agent_service.config import get_settings
from agent_service.models.store import get_decrypted_api_key, get_provider_row


class UnknownModelProviderError(ValueError):
    pass


class ProviderNotConfiguredError(ValueError):
    """Provedor reconhecido, mas sem chave cadastrada em `/model-providers`."""


def _credentials(provider: str) -> tuple[str | None, str | None]:
    """(api_key decifrada, base_url) salvos para o provedor — `None` se não configurado."""
    row = get_provider_row(provider)
    return get_decrypted_api_key(provider), (row["base_url"] if row else None)


def get_model(provider: str | None = None, model_id: str | None = None) -> Model:
    settings = get_settings()
    provider = (provider or settings.default_model_provider).lower()
    model_id = model_id or settings.default_model_id

    if provider == "google":
        from agno.models.google import Gemini

        api_key, _ = _credentials("google")
        return Gemini(id=model_id, api_key=api_key or settings.google_api_key)

    if provider == "openai":
        from agno.models.openai import OpenAIChat

        api_key, base_url = _credentials("openai")
        if not api_key:
            raise ProviderNotConfiguredError("openai: nenhuma chave cadastrada em /model-providers")
        return OpenAIChat(id=model_id, api_key=api_key, base_url=base_url or None)

    if provider == "anthropic":
        from agno.models.anthropic import Claude

        api_key, _ = _credentials("anthropic")
        if not api_key:
            raise ProviderNotConfiguredError("anthropic: nenhuma chave cadastrada em /model-providers")
        return Claude(id=model_id, api_key=api_key)

    if provider == "ollama":
        from agno.models.ollama import Ollama

        _, base_url = _credentials("ollama")
        return Ollama(id=model_id, host=base_url or None)

    raise UnknownModelProviderError(
        f"Provedor de modelo desconhecido: {provider!r}. "
        "Adicione um novo branch em agent_service.models.provider.get_model."
    )
