"""Modelos disponíveis em cada provedor, lidos da API dele — não de uma lista fixa.

Provedores lançam e aposentam modelos o tempo todo (o `gemini-2.5-flash-lite`
saiu do ar para contas novas no meio de um teste nosso). Por isso o console
pergunta ao provedor, com a credencial cadastrada, quais modelos existem:

- google: `models.list` do Gemini — só os que fazem `generateContent`;
- openai: `GET /v1/models` — só os de chat (sem embedding, áudio, imagem...);
- anthropic: `GET /v1/models`;
- ollama: `GET /api/tags` do servidor configurado.

O resultado fica em cache por credencial (`CACHE_SECONDS`): listar modelos não
gasta token, mas é uma chamada externa a cada abertura do formulário.
"""

import re
import time
from dataclasses import dataclass
from typing import Any

from agent_service.models.catalog import ProviderProbeError

CACHE_SECONDS = 15 * 60

_OPENAI_CHAT = re.compile(r"^(gpt-|o\d|chatgpt-)")
_OPENAI_NOT_CHAT = ("audio", "realtime", "transcribe", "tts", "image", "search", "instruct", "embedding", "moderation", "codex")
_GOOGLE_NOT_CHAT = ("transcribe", "embedding", "tts", "image", "live", "native-audio", "aqa", "imagen", "veo", "robotics", "computer-use")


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str
    created: int | None = None
    """Timestamp (s) de criação, quando o provedor informa — para ordenar os mais novos primeiro."""


_cache: dict[tuple[str, str | None], tuple[float, list[ModelInfo]]] = {}


def _google(api_key: str | None, base_url: str | None) -> list[ModelInfo]:
    from google.genai import Client
    from google.genai.errors import ClientError

    # O cliente precisa viver até o fim da paginação: um `Client(...)` temporário
    # é coletado no meio e a página seguinte falha com "client has been closed".
    client = Client(api_key=api_key)
    try:
        items = list(client.models.list(config={"page_size": 200}))
    except ClientError as exc:
        raise ProviderProbeError(str(exc)) from exc
    models = []
    for m in items:
        model_id = (m.name or "").removeprefix("models/")
        actions = [a.lower() for a in (getattr(m, "supported_actions", None) or [])]
        if not model_id.startswith("gemini") or (actions and "generatecontent" not in actions):
            continue
        if any(word in model_id for word in _GOOGLE_NOT_CHAT):
            continue
        models.append(ModelInfo(id=model_id, label=getattr(m, "display_name", None) or model_id))
    return models


def _openai(api_key: str | None, base_url: str | None) -> list[ModelInfo]:
    from openai import OpenAI, OpenAIError

    try:
        items = list(OpenAI(api_key=api_key, base_url=base_url or None).models.list())
    except OpenAIError as exc:
        raise ProviderProbeError(str(exc)) from exc
    return [
        ModelInfo(id=m.id, label=m.id, created=getattr(m, "created", None))
        for m in items
        if _OPENAI_CHAT.match(m.id) and not any(word in m.id for word in _OPENAI_NOT_CHAT)
    ]


def _anthropic(api_key: str | None, base_url: str | None) -> list[ModelInfo]:
    from anthropic import Anthropic, AnthropicError

    try:
        items = list(Anthropic(api_key=api_key).models.list(limit=100))
    except AnthropicError as exc:
        raise ProviderProbeError(str(exc)) from exc
    return [
        ModelInfo(
            id=m.id,
            label=getattr(m, "display_name", None) or m.id,
            created=int(m.created_at.timestamp()) if getattr(m, "created_at", None) else None,
        )
        for m in items
    ]


def _ollama(api_key: str | None, base_url: str | None) -> list[ModelInfo]:
    import httpx

    url = (base_url or "http://localhost:11434").rstrip("/")
    try:
        response = httpx.get(f"{url}/api/tags", timeout=5)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ProviderProbeError(f"Não foi possível falar com o Ollama em {url}: {exc}") from exc
    return [ModelInfo(id=m["name"], label=m["name"]) for m in response.json().get("models", []) if m.get("name")]


_LISTERS = {"google": _google, "openai": _openai, "anthropic": _anthropic, "ollama": _ollama}


def list_models(
    provider: str, *, api_key: str | None, base_url: str | None, cache_key: str | None, refresh: bool = False
) -> tuple[list[ModelInfo], float]:
    """Modelos do provedor, os mais novos primeiro, e quando foram lidos (epoch)."""
    lister = _LISTERS.get(provider)
    if lister is None:
        raise ProviderProbeError(f"Provedor sem listagem de modelos: {provider!r}")
    key = (provider, cache_key)
    cached = _cache.get(key)
    if cached and not refresh and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1], cached[0]
    models = lister(api_key, base_url)
    # Mais novos primeiro quando há data; senão ordem alfabética decrescente, que
    # nos nomes versionados ("gemini-3...", "gemini-2.5...") dá o mesmo efeito.
    models.sort(key=lambda m: (m.created or 0, m.id), reverse=True)
    fetched_at = time.time()
    _cache[key] = (fetched_at, models)
    return models, fetched_at


def clear_cache() -> None:
    _cache.clear()


def as_dict(model: ModelInfo) -> dict[str, Any]:
    return {"id": model.id, "label": model.label, "created": model.created}
