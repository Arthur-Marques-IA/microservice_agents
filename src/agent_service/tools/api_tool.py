"""Tools `kind="api"`: chamam uma API HTTP existente, descrita em JSON — sem
escrever código. `config` diz o método, a URL (com placeholders `{nome}` para
parâmetros de path), os parâmetros que o modelo preenche e a autenticação.

`build_api_function` monta um `agno.tools.function.Function` com `parameters`
(o JSON Schema que o modelo vê) e `entrypoint` explícitos — o Agno chama
`entrypoint(**argumentos)` diretamente, sem inspecionar uma assinatura Python
real (`skip_entrypoint_processing=True`), que é o mecanismo que permite uma
tool inteiramente definida por dados.
"""

from typing import Any, Literal

import httpx
from agno.tools.function import Function

Method = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
ParamLocation = Literal["query", "path", "header", "body"]
ParamType = Literal["string", "integer", "number", "boolean", "object", "array"]
AuthType = Literal["none", "bearer", "api_key", "basic"]

_JSON_SCHEMA_TYPE: dict[ParamType, str] = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "object": "object",
    "array": "array",
}
_METHODS: set[str] = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_MAX_RESPONSE_CHARS = 8000
_DEFAULT_TIMEOUT_SECONDS = 15.0
_MAX_TIMEOUT_SECONDS = 60.0


class ApiToolConfigError(ValueError):
    """`config` inválido — reportado como 422 na criação/edição da tool."""


def validate_api_config(config: dict[str, Any]) -> dict[str, Any]:
    """Normaliza e valida `config`; levanta `ApiToolConfigError` com uma
    mensagem específica do primeiro problema encontrado."""
    method = str(config.get("method", "GET")).upper()
    if method not in _METHODS:
        raise ApiToolConfigError(f"method deve ser um de {sorted(_METHODS)}")

    url = config.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ApiToolConfigError("url deve ser http(s)://...")

    parameters = config.get("parameters", [])
    if not isinstance(parameters, list):
        raise ApiToolConfigError("parameters deve ser uma lista")
    seen_names: set[str] = set()
    path_names: set[str] = set()
    for p in parameters:
        name = p.get("name")
        if not isinstance(name, str) or not name.isidentifier():
            raise ApiToolConfigError(f"nome de parâmetro inválido: {name!r}")
        if name in seen_names:
            raise ApiToolConfigError(f"parâmetro duplicado: {name!r}")
        seen_names.add(name)
        if p.get("type") not in _JSON_SCHEMA_TYPE:
            raise ApiToolConfigError(f"tipo inválido em {name!r}: {p.get('type')!r}")
        location = p.get("location", "query")
        if location not in ("query", "path", "header", "body"):
            raise ApiToolConfigError(f"location inválido em {name!r}: {location!r}")
        if location == "path":
            path_names.add(name)

    for placeholder in _format_placeholders(url):
        if placeholder not in path_names:
            raise ApiToolConfigError(
                f"a url referencia {{{placeholder}}}, mas não há parâmetro location=path com esse nome"
            )

    auth = config.get("auth") or {"type": "none"}
    auth_type = auth.get("type", "none")
    if auth_type not in ("none", "bearer", "api_key", "basic"):
        raise ApiToolConfigError(f"auth.type inválido: {auth_type!r}")
    if auth_type == "bearer" and not auth.get("token"):
        raise ApiToolConfigError("auth.token é obrigatório para auth.type='bearer'")
    if auth_type == "api_key" and not (auth.get("header") and auth.get("value")):
        raise ApiToolConfigError("auth.header e auth.value são obrigatórios para auth.type='api_key'")
    if auth_type == "basic" and not (auth.get("username") and auth.get("password")):
        raise ApiToolConfigError("auth.username e auth.password são obrigatórios para auth.type='basic'")

    timeout = config.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
    if not isinstance(timeout, (int, float)) or not (0 < timeout <= _MAX_TIMEOUT_SECONDS):
        raise ApiToolConfigError(f"timeout_seconds deve ser > 0 e <= {_MAX_TIMEOUT_SECONDS}")

    headers = config.get("headers", {})
    if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
        raise ApiToolConfigError("headers deve ser um objeto string -> string")

    return {
        "method": method,
        "url": url,
        "parameters": parameters,
        "headers": headers,
        "auth": auth,
        "timeout_seconds": float(timeout),
    }


def _format_placeholders(url: str) -> set[str]:
    import string

    return {name for _, name, _, _ in string.Formatter().parse(url) if name}


def _parameters_schema(parameters: list[dict[str, Any]]) -> dict[str, Any]:
    properties = {}
    required = []
    for p in parameters:
        properties[p["name"]] = {
            "type": _JSON_SCHEMA_TYPE[p["type"]],
            "description": p.get("description") or "",
        }
        if p.get("required"):
            required.append(p["name"])
    return {"type": "object", "properties": properties, "required": required}


def _apply_auth(headers: dict[str, str], params: dict[str, Any], auth: dict[str, Any]) -> None:
    auth_type = auth.get("type", "none")
    if auth_type == "bearer":
        headers["Authorization"] = f"Bearer {auth['token']}"
    elif auth_type == "api_key":
        headers[auth["header"]] = auth["value"]
    elif auth_type == "basic":
        pass  # aplicado via httpx.BasicAuth na chamada, não num header manual


def _call_api(config: dict[str, Any], arguments: dict[str, Any]) -> str:
    method = config["method"]
    url = config["url"]
    headers = dict(config.get("headers") or {})
    query: dict[str, Any] = {}
    path_values: dict[str, Any] = {}
    body: dict[str, Any] = {}

    for p in config["parameters"]:
        name = p["name"]
        if name not in arguments:
            continue
        value = arguments[name]
        location = p.get("location", "query")
        if location == "query":
            query[name] = value
        elif location == "path":
            path_values[name] = value
        elif location == "header":
            headers[str(name)] = str(value)
        elif location == "body":
            body[name] = value

    try:
        url = url.format(**path_values)
    except KeyError as exc:
        return f"Erro ao montar a URL: parâmetro de path ausente {exc}"

    auth = config.get("auth") or {"type": "none"}
    _apply_auth(headers, query, auth)
    basic_auth = httpx.BasicAuth(auth["username"], auth["password"]) if auth.get("type") == "basic" else None

    try:
        response = httpx.request(
            method,
            url,
            params=query or None,
            json=body or None,
            headers=headers or None,
            auth=basic_auth,
            timeout=config.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS),
        )
    except httpx.HTTPError as exc:
        return f"Falha ao chamar a API: {exc}"

    text = response.text
    try:
        import json

        text = json.dumps(response.json(), ensure_ascii=False)
    except ValueError:
        pass
    if len(text) > _MAX_RESPONSE_CHARS:
        text = text[:_MAX_RESPONSE_CHARS] + f"... (truncado, {len(response.text)} chars no total)"
    return f"HTTP {response.status_code}: {text}"


def build_api_function(*, tool_name: str, description: str | None, config: dict[str, Any]) -> Function:
    validated = validate_api_config(config)

    def entrypoint(**arguments: Any) -> str:
        return _call_api(validated, arguments)

    return Function(
        name=tool_name,
        description=description or f"Chama {validated['method']} {validated['url']}",
        parameters=_parameters_schema(validated["parameters"]),
        entrypoint=entrypoint,
        skip_entrypoint_processing=True,
    )
