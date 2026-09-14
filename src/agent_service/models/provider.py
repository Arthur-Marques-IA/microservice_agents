"""Abstração de gerenciamento de modelos.

Isola o resto do serviço de qual SDK/provedor de LLM está por trás de um agente.
Hoje só resolve o provider "google" (Gemini); novos provedores (OpenAI, Anthropic,
Ollama/vLLM) entram aqui como mais um branch, sem mexer em código de agente.
"""

from agno.models.base import Model

from agent_service.config import get_settings


class UnknownModelProviderError(ValueError):
    pass


def get_model(provider: str | None = None, model_id: str | None = None) -> Model:
    settings = get_settings()
    provider = (provider or settings.default_model_provider).lower()
    model_id = model_id or settings.default_model_id

    if provider == "google":
        from agno.models.google import Gemini

        return Gemini(id=model_id, api_key=settings.google_api_key)

    raise UnknownModelProviderError(
        f"Provedor de modelo desconhecido: {provider!r}. "
        "Adicione um novo branch em agent_service.models.provider.get_model."
    )
