"""Segredos das tools (`{{secret:NOME}}`): cadastrar, listar e remover.

A leitura devolve só nome, descrição, datas e quais tools usam cada um — o valor nunca
sai do serviço depois de gravado (ver `tools/secrets.py`). Escopo admin, como o resto.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_service.tools import secrets, store

router = APIRouter(prefix="/secrets", tags=["secrets"])


class SecretIn(BaseModel):
    value: str = Field(..., min_length=1, description="O valor. Não volta em nenhuma leitura.")
    description: str | None = None


class SecretOut(BaseModel):
    name: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    used_by: list[str] = Field(default_factory=list, description="Tools que referenciam o segredo.")


class SecretSetOut(BaseModel):
    name: str
    created: bool
    hint: str
    """Os 4 últimos caracteres, para conferir que gravou o valor certo."""


def _usage() -> dict[str, list[str]]:
    used: dict[str, list[str]] = {}
    for tool in store.list_tools():
        for name in secrets.references(tool.get("config") or {}):
            used.setdefault(name, []).append(tool["tool_name"])
    return used


@router.get("", response_model=list[SecretOut])
def list_secrets() -> list[dict[str, Any]]:
    used = _usage()
    return [{**row, "used_by": sorted(used.get(row["name"], []))} for row in secrets.list_secrets()]


@router.put("/{name}", response_model=SecretSetOut)
def set_secret(name: str, body: SecretIn) -> dict[str, Any]:
    try:
        return secrets.set_secret(name, body.value, body.description)
    except secrets.SecretError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{name}", status_code=204)
def delete_secret(name: str) -> None:
    using = sorted(_usage().get(name, []))
    if using:
        raise HTTPException(
            status_code=409,
            detail=f"o segredo {name!r} está em uso por: {', '.join(using)}. Tire a referência dessas tools antes.",
        )
    if not secrets.delete_secret(name):
        raise HTTPException(status_code=404, detail=f"segredo {name!r} não encontrado")
