"""Parâmetros de geração por agente, num vocabulário só para todos os provedores.

```json
{"temperature": 0.3, "top_p": 0.9, "max_tokens": 2048, "reasoning": "low"}
```

Cada provedor chama isso de um jeito (`max_output_tokens` no Gemini,
`max_completion_tokens` no OpenAI, `options.num_predict` no Ollama); a tradução
fica em `provider_kwargs`, para o resto do serviço não saber disso.

`reasoning` é o nível de raciocínio — `off`, `low`, `medium`, `high` ou ausente
(padrão do modelo) — num vocabulário só, traduzido para o que cada modelo aceita
(verificado contra a API em 2026-09-26):

- Gemini 3 em diante (e os apelidos `-latest`): `thinking_level` —
  `off` = `minimal` (zero tokens de raciocínio), os outros com o mesmo nome;
- Gemini 2.x: não aceita `thinking_level`, só orçamento em tokens —
  `off`=0 (128 no Pro, que não desliga), `low`=1024, `medium`=4096, `high`=16384;
- OpenAI: `reasoning_effort` (`off` = `minimal`), só nos modelos de raciocínio
  (`o*`, `gpt-5*`) — nos outros não há o que ajustar e o nível é ignorado.

Anthropic e Ollama ainda não: são recusados no cadastro, em vez de ignorados.
`thinking_budget` (Gemini) continua aceito como ajuste fino e, quando vem junto,
vale no lugar do nível.
"""

from typing import Any

PARAM_RANGES: dict[str, tuple[type, float, float]] = {
    "temperature": (float, 0.0, 2.0),
    "top_p": (float, 0.0, 1.0),
    "max_tokens": (int, 1, 200_000),
    "thinking_budget": (int, 0, 32_768),
}

REASONING_LEVELS = ("off", "low", "medium", "high")
_GEMINI2_BUDGET = {"off": 0, "low": 1024, "medium": 4096, "high": 16384}


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
        if name == "reasoning":
            if value is None or value == "auto":
                continue
            if value not in REASONING_LEVELS:
                raise ModelParamsError(f"model_params.reasoning deve ser um de {list(REASONING_LEVELS)} (ou vazio)")
            if (provider or "google").lower() not in ("google", "openai"):
                raise ModelParamsError("model_params.reasoning ainda só vale para google e openai")
            normalized[name] = value
            continue
        if name not in PARAM_RANGES:
            raise ModelParamsError(f"model_params.{name} não existe (use {sorted([*PARAM_RANGES, 'reasoning'])})")
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


def _reasoning_kwargs(provider: str, model_id: str, level: str) -> dict[str, Any]:
    model = model_id.lower()
    if provider == "google":
        if model.startswith("gemini-2") or model.startswith("gemini-1"):
            budget = _GEMINI2_BUDGET[level]
            if level == "off" and "pro" in model:
                budget = 128  # o 2.5 Pro não desliga o raciocínio; 128 é o mínimo aceito
            return {"thinking_budget": budget}
        return {"thinking_level": "minimal" if level == "off" else level}
    if provider == "openai" and (model.startswith("o") or model.startswith("gpt-5")):
        return {"reasoning_effort": "minimal" if level == "off" else level}
    return {}


def provider_kwargs(provider: str, params: dict[str, Any] | None, model_id: str = "") -> dict[str, Any]:
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
    if params.get("reasoning") and "thinking_budget" not in params:
        kwargs.update(_reasoning_kwargs(provider, model_id, params["reasoning"]))
    if "thinking_budget" in params and provider == "google":
        kwargs["thinking_budget"] = params["thinking_budget"]
    return kwargs
