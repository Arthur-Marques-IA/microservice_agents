"""O `output_schema` (pydantic) de um agente `kind="analysis"`, montado a partir
de `response_schema`.

Os campos folha (`string`, `integer`, `number`, `boolean`) têm a mesma forma de
`dependency_fields` e são normalizados pelo mesmo
`dependency_fields.validate_field_specs` — um formato só para descrever campo.

Além deles, a saída aceita dois tipos compostos, que `dependency_fields` não
tem: `object` (com `fields`) e `array` (com `items`). É o que permite extrair
uma lista de itens de um documento — as parcelas de um contrato, as mensagens
de um histórico de conversa — em vez de só campos soltos.

```json
{"name": "parcelas", "type": "array",
 "items": {"type": "object", "fields": [{"name": "numero", "type": "integer", "required": true},
                                        {"name": "valor",  "type": "number",  "required": true}]}}
{"name": "cliente", "type": "object", "fields": [{"name": "nome", "type": "string"}]}
{"name": "tags",    "type": "array",  "items": {"type": "string"}}
```

`fields` e `items` são **obrigatórios** nos seus tipos, não por preciosismo: um
`object` sem `fields` vira `{"type": "object", "additionalProperties": true}` no
JSON Schema e um `array` sem `items` vira `"items": {}` — as duas formas que os
provedores recusam em saída estruturada (o Gemini exige `properties` em OBJECT e
um `items` tipado em ARRAY). Um schema assim seria aceito no cadastro e falharia
em toda chamada.
"""

from typing import Any

from pydantic import BaseModel, Field, create_model

from agent_service.agents.dependency_fields import DependencyFieldSpecError, validate_field_specs

_PY_TYPES: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}

LEAF_TYPES = frozenset(_PY_TYPES)
RESPONSE_TYPES = LEAF_TYPES | {"object", "array"}
ITEM_TYPES = LEAF_TYPES | {"object"}
"""`array` de `array` fica de fora: aninhar listas direto raramente é o que se
quer (o caso real é lista de objetos) e complica o schema para o modelo."""

_MAX_DEPTH = 5


class ResponseSchemaError(ValueError):
    """`response_schema` inválido — 422 ao criar/editar o agente."""


def validate_response_schema(specs: list[dict[str, Any]] | None, *, _depth: int = 0, _path: str = "response_schema") -> list[dict[str, Any]]:
    """Valida e normaliza `response_schema`, incluindo os tipos compostos."""
    if not specs:
        return []
    if not isinstance(specs, list):
        raise ResponseSchemaError(f"{_path} deve ser uma lista")
    if _depth > _MAX_DEPTH:
        raise ResponseSchemaError(f"{_path}: aninhamento passa de {_MAX_DEPTH} níveis")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in specs:
        field = _validate_field(raw, depth=_depth, path=_path)
        if field["name"] in seen:
            raise ResponseSchemaError(f"{_path}: campo duplicado {field['name']!r}")
        seen.add(field["name"])
        normalized.append(field)
    return normalized


def _validate_field(raw: dict[str, Any], *, depth: int, path: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ResponseSchemaError(f"{path}: cada campo deve ser um objeto")
    field_type = raw.get("type", "string")
    if field_type not in RESPONSE_TYPES:
        raise ResponseSchemaError(
            f"{path}: tipo inválido {field_type!r} em {raw.get('name')!r} (use {sorted(RESPONSE_TYPES)})"
        )

    # Os campos folha são exatamente os de `dependency_fields`: mesma normalização,
    # para não existirem dois formatos de "descrever um campo" no produto.
    base = _leaf(raw, path=path) if field_type in LEAF_TYPES else _composite_base(raw, path=path)
    if field_type in LEAF_TYPES:
        return base

    nome = base["name"]
    if field_type == "object":
        subcampos = raw.get("fields")
        if not subcampos:
            raise ResponseSchemaError(
                f"{path}.{nome}: type='object' exige `fields` (um objeto sem campos não vira schema válido "
                "para o modelo — veja o docstring de agents/response_model.py)"
            )
        base["fields"] = validate_response_schema(subcampos, _depth=depth + 1, _path=f"{path}.{nome}.fields")
        return base

    items = raw.get("items")
    if not isinstance(items, dict):
        raise ResponseSchemaError(
            f"{path}.{nome}: type='array' exige `items` com o tipo do elemento, ex.: "
            '{"type": "string"} ou {"type": "object", "fields": [...]}'
        )
    item_type = items.get("type", "string")
    if item_type not in ITEM_TYPES:
        raise ResponseSchemaError(
            f"{path}.{nome}.items: tipo inválido {item_type!r} (use {sorted(ITEM_TYPES)})"
        )
    normalized_items: dict[str, Any] = {"type": item_type}
    if item_type == "object":
        if not items.get("fields"):
            raise ResponseSchemaError(f"{path}.{nome}.items: type='object' exige `fields`")
        normalized_items["fields"] = validate_response_schema(
            items["fields"], _depth=depth + 1, _path=f"{path}.{nome}.items.fields"
        )
    base["items"] = normalized_items
    return base


def _leaf(raw: dict[str, Any], *, path: str) -> dict[str, Any]:
    try:
        return validate_field_specs([raw])[0]
    except DependencyFieldSpecError as exc:
        raise ResponseSchemaError(f"{path}: {exc}") from exc


def _composite_base(raw: dict[str, Any], *, path: str) -> dict[str, Any]:
    """O mesmo que `_leaf` faria, mas sem passar pelo validador de folha, que só
    conhece os quatro tipos simples."""
    name = raw.get("name")
    if not isinstance(name, str) or not name.isidentifier():
        raise ResponseSchemaError(f"{path}: nome de campo inválido: {name!r}")
    return {
        "name": name,
        "type": raw["type"],
        "label": raw.get("label") or name,
        "description": raw.get("description") or "",
        "required": bool(raw.get("required", False)),
        "default": None,  # composto não tem default: a ausência já é `None`
    }


def _model_name(*parts: str) -> str:
    """Nome único por caminho, só para facilitar debug — aparece no schema e nos
    erros de validação, e não tem efeito em runtime."""
    return "".join(
        "".join(p.capitalize() for p in part.replace("-", "_").split("_")) for part in parts if part
    ) or "Analysis"


def _annotation(field: dict[str, Any], prefix: str) -> Any:
    field_type = field["type"]
    if field_type == "object":
        return _model(field["fields"], _model_name(prefix, field["name"]))
    if field_type == "array":
        items = field["items"]
        if items["type"] == "object":
            return list[_model(items["fields"], _model_name(prefix, field["name"], "item"))]  # type: ignore[misc]
        return list[_PY_TYPES[items["type"]]]  # type: ignore[misc]
    return _PY_TYPES[field_type]


def _model(fields: list[dict[str, Any]], name: str) -> type[BaseModel]:
    model_fields: dict[str, Any] = {}
    for f in fields:
        annotation = _annotation(f, name)
        description = f.get("description") or f.get("label") or f["name"]
        if f.get("required"):
            model_fields[f["name"]] = (annotation, Field(..., description=description))
        else:
            model_fields[f["name"]] = (annotation | None, Field(default=f.get("default"), description=description))
    return create_model(name, **model_fields)


def build_response_model(agent_type: str, fields: list[dict[str, Any]]) -> type[BaseModel]:
    return _model(fields, _model_name(agent_type) + "Output")
