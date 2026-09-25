"""Parâmetros de geração por agente, num vocabulário só para todos os provedores.

```json
{"temperature": 0.3, "top_p": 0.9, "max_tokens": 2048, "thinking_budget": 0}
```

Cada provedor chama isso de um jeito (`max_output_tokens` no Gemini,
`max_completion_tokens` no OpenAI, `options.num_predict` no Ollama); a tradução
fica em `provider_kwargs`, para o resto do serviço não saber disso.

`thinking_budget` só existe no Gemini 2.5 ("thinking"): 0 desliga o raciocínio,
o que corta latência e custo em decisões simples. Nos outros provedores é
recusado no cadastro, em vez de ser ignorado calado.
"""

from typing import Any

PARAM_RANGES: dict[str, tuple[type, float, float]] = {
    "temperature": (float, 0.0, 2.0),
    "top_p": (float, 0.0, 1.0),
    "max_tokens": (int, 1, 200_000),
    "thinking_budget": (int, 0, 32_768),
}


class ModelParamsError(ValueError):
    """Parâmetro desconhecido ou fora da faixa — 422 no cadastro do agente."""


def validate_model_params(params: Any, provider: str | None) -> dict[str, Any] | None:
    """Normaliza os parâmetros. `None`/`{}` = padrão do provedor (nada gravado)."""
    if params is None or params == {}:
        return None
    if not isinstance(params, dict):
        raise ModelParamsError("model_params deve ser um objeto, ex.: {\"temperature\": 0.3}")
    normalized: dict[str, Any] = {}
    for name, value in params.items():
        if name not in PARAM_RANGES:
            raise ModelParamsError(f"model_params.{name} não existe (use {sorted(PARAM_RANGES)})")
        if value is None:
            continue
        kind, low, high = PARAM_RANGES[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (kind is int and not float(value).is_integer()):
            raise ModelParamsError(f"model_params.{name} deve ser {'inteiro' if kind is int else 'número'}")
        if not low <= value <= high:
            raise ModelParamsError(f"model_params.{name} deve estar entre {low:g} e {high:g}")
        normalized[name] = kind(value)
    if "thinking_budget" in normalized and (provider or "google").lower() != "google":
        raise ModelParamsError("model_params.thinking_budget só vale para o provedor google (Gemini 2.5)")
    return normalized or None


def provider_kwargs(provider: str, params: dict[str, Any] | None) -> dict[str, Any]:
    """Os parâmetros no nome que o modelo do Agno de cada provedor espera."""
    if not params:
        return {}
    kwargs: dict[str, Any] = {}
    if provider == "ollama":
        options = {}
        if "temperature" in params:
            options["temperature"] = params["temperature"]
        if "top_p" in params:
            options["top_p"] = params["top_p"]
        if "max_tokens" in params:
            options["num_predict"] = params["max_tokens"]
        return {"options": options} if options else {}
    for name in ("temperature", "top_p"):
        if name in params:
            kwargs[name] = params[name]
    if "max_tokens" in params:
        key = {"google": "max_output_tokens", "openai": "max_completion_tokens"}.get(provider, "max_tokens")
        kwargs[key] = params["max_tokens"]
    if "thinking_budget" in params and provider == "google":
        kwargs["thinking_budget"] = params["thinking_budget"]
    return kwargs
