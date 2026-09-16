"""Provedores de modelo suportados: o que cada um precisa (chave, base_url) e
como validar a chave sem gastar tokens de verdade — `probe` chama um endpoint
de leitura barato (listar modelos) do SDK oficial do provedor.

Adicionar um provedor novo: um branch aqui + um branch em `provider.get_model`.
"""

from dataclasses import dataclass
from typing import Protocol


class ProviderProbeError(RuntimeError):
    """A chave (ou o endpoint) não passou na validação — mensagem já é apresentável."""


class Probe(Protocol):
    def __call__(self, *, api_key: str | None, base_url: str | None) -> None: ...


@dataclass(frozen=True)
class ProviderSpec:
    provider: str
    label: str
    requires_api_key: bool
    supports_custom_base_url: bool
    default_model_id: str
    docs_url: str
    probe: Probe


def _probe_google(*, api_key: str | None, base_url: str | None) -> None:
    from google.genai import Client
    from google.genai.errors import ClientError

    try:
        client = Client(api_key=api_key)
        next(iter(client.models.list(config={"page_size": 1})), None)
    except ClientError as exc:
        raise ProviderProbeError(str(exc)) from exc


def _probe_openai(*, api_key: str | None, base_url: str | None) -> None:
    from openai import AuthenticationError, OpenAI, OpenAIError

    try:
        client = OpenAI(api_key=api_key, base_url=base_url or None)
        next(iter(client.models.list()), None)
    except AuthenticationError as exc:
        raise ProviderProbeError(str(exc)) from exc
    except OpenAIError as exc:
        raise ProviderProbeError(str(exc)) from exc


def _probe_anthropic(*, api_key: str | None, base_url: str | None) -> None:
    from anthropic import AnthropicError, AuthenticationError, Anthropic

    try:
        client = Anthropic(api_key=api_key)
        next(iter(client.models.list(limit=1)), None)
    except AuthenticationError as exc:
        raise ProviderProbeError(str(exc)) from exc
    except AnthropicError as exc:
        raise ProviderProbeError(str(exc)) from exc


def _probe_ollama(*, api_key: str | None, base_url: str | None) -> None:
    import httpx

    url = (base_url or "http://localhost:11434").rstrip("/")
    try:
        response = httpx.get(f"{url}/api/tags", timeout=5)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ProviderProbeError(f"Não foi possível falar com o Ollama em {url}: {exc}") from exc


PROVIDERS: dict[str, ProviderSpec] = {
    "google": ProviderSpec(
        provider="google",
        label="Google (Gemini)",
        requires_api_key=True,
        supports_custom_base_url=False,
        default_model_id="gemini-2.5-flash",
        docs_url="https://aistudio.google.com/app/apikey",
        probe=_probe_google,
    ),
    "openai": ProviderSpec(
        provider="openai",
        label="OpenAI",
        requires_api_key=True,
        supports_custom_base_url=True,
        default_model_id="gpt-4.1-mini",
        docs_url="https://platform.openai.com/api-keys",
        probe=_probe_openai,
    ),
    "anthropic": ProviderSpec(
        provider="anthropic",
        label="Anthropic (Claude)",
        requires_api_key=True,
        supports_custom_base_url=False,
        default_model_id="claude-sonnet-4-5",
        docs_url="https://console.anthropic.com/settings/keys",
        probe=_probe_anthropic,
    ),
    "ollama": ProviderSpec(
        provider="ollama",
        label="Ollama (local/self-hosted)",
        requires_api_key=False,
        supports_custom_base_url=True,
        default_model_id="llama3.1",
        docs_url="https://ollama.com/",
        probe=_probe_ollama,
    ),
}


def get_provider_spec(provider: str) -> ProviderSpec | None:
    return PROVIDERS.get(provider)
