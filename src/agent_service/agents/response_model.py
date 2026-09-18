"""Monta o `output_schema` (pydantic) de um agente `kind="analysis"` a partir
de `response_schema` — mesma forma normalizada de `dependency_fields`
(`dependency_fields.validate_field_specs`), reaproveitada aqui em vez de um
segundo formato de "lista de campos" para descrever.
"""

from typing import Any

from pydantic import BaseModel, Field, create_model

_PY_TYPES: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}


def build_response_model(agent_type: str, fields: list[dict[str, Any]]) -> type[BaseModel]:
    model_fields: dict[str, Any] = {}
    for f in fields:
        py_type = _PY_TYPES[f["type"]]
        description = f.get("description") or f.get("label") or f["name"]
        if f.get("required"):
            model_fields[f["name"]] = (py_type, Field(..., description=description))
        else:
            model_fields[f["name"]] = (py_type | None, Field(default=f.get("default"), description=description))
    # Nome único por agente só para facilitar debug (schema/erros mostram o nome) —
    # não tem efeito em runtime além disso.
    model_name = "".join(part.capitalize() for part in agent_type.replace("-", "_").split("_")) + "Output"
    return create_model(model_name or "AnalysisOutput", **model_fields)
