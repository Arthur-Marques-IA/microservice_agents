"""CRUD de definições de agente + histórico de prompt (read-only).

Separado do contrato de chat (`api/routes.py`) porque é uma superfície
diferente: isso é gerenciamento (usado pela tela `/agents` do frontend e por
integrações administrativas), não o contrato estável de execução que outros
módulos da plataforma consomem. Tools têm CRUD próprio em `tools_routes.py`
(`GET /tools` etc.) — aqui só se valida que os nomes em `tools` existem.
"""

import re
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from agent_service.agents.dependency_fields import (
    DependencyFieldSpecError,
    FieldType,
    validate_field_specs,
)
from agent_service.agents.store import (
    DefinitionNotFoundError,
    create_definition,
    delete_definition,
    get_definition,
    list_definitions,
    list_prompt_versions,
    update_definition,
)
from agent_service.documents.collections import collection_exists
from agent_service.tools.api_tool import required_dependencies
from agent_service.tools.registry import tool_exists
from agent_service.tools.store import get_tool

router = APIRouter(prefix="/agents", tags=["agents"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class DependencyFieldIn(BaseModel):
    name: str
    type: FieldType = "string"
    label: str | None = None
    description: str | None = None
    required: bool = False
    default: Any = None


class DependencyFieldOut(BaseModel):
    name: str
    type: FieldType
    label: str
    description: str
    required: bool
    default: Any


class AgentDefinitionIn(BaseModel):
    agent_type: str = Field(..., description="Slug estável, usado como agent_id no /chat")
    name: str
    instructions: list[str] = Field(..., min_length=1)
    tools: list[str] = []
    model_provider: str | None = None
    model_id: str | None = None
    model_credential_id: str | None = None
    knowledge_collection: str | None = Field(
        default=None, description="Collection de documentos que o agente pode consultar (GET /collections)"
    )
    dependency_fields: list[DependencyFieldIn] = []
    memory_backend: Literal["common", "mem0"] = "common"
    num_history_runs: int = 10

    @field_validator("agent_type")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("agent_type deve ser um slug: letras minúsculas, números, '-' ou '_'")
        return v

    @field_validator("dependency_fields")
    @classmethod
    def _validate_dependency_fields(cls, v: list[DependencyFieldIn]) -> list[DependencyFieldIn]:
        _normalize_dependency_fields(v)
        return v


class AgentDefinitionUpdate(BaseModel):
    name: str | None = None
    instructions: list[str] | None = Field(default=None, min_length=1)
    tools: list[str] | None = None
    model_provider: str | None = None
    model_id: str | None = None
    model_credential_id: str | None = None
    knowledge_collection: str | None = None
    dependency_fields: list[DependencyFieldIn] | None = None
    memory_backend: Literal["common", "mem0"] | None = None
    num_history_runs: int | None = None

    @field_validator("dependency_fields")
    @classmethod
    def _validate_dependency_fields(cls, v: list[DependencyFieldIn] | None) -> list[DependencyFieldIn] | None:
        if v is not None:
            _normalize_dependency_fields(v)
        return v


class AgentDefinitionOut(BaseModel):
    agent_type: str
    name: str
    instructions: list[str]
    tools: list[str]
    model_provider: str | None
    model_id: str | None
    model_credential_id: str | None = None
    knowledge_collection: str | None = None
    dependency_fields: list[DependencyFieldOut]
    memory_backend: str
    num_history_runs: int
    is_seed: bool
    prompt_version: int
    created_at: datetime
    updated_at: datetime


def _normalize_dependency_fields(fields: list[DependencyFieldIn]) -> list[dict[str, Any]]:
    try:
        return validate_field_specs([f.model_dump() for f in fields])
    except DependencyFieldSpecError as exc:
        raise ValueError(str(exc)) from exc


class PromptVersionOut(BaseModel):
    version: int
    instructions: list[str]
    created_at: datetime


def _validate_collection(name: str | None) -> None:
    if name is not None and not collection_exists(name):
        raise HTTPException(status_code=422, detail=f"Collection desconhecida: {name!r} (veja GET /collections)")


def _validate_tools(names: list[str], declared_dependencies: set[str]) -> None:
    """Confere que os nomes existem em `tool_definitions` e que o agente declara
    as dependências que as tools exigem (parâmetros `source="dependency"`
    obrigatórios). Construir a tool de fato fica pra hora do `/chat`
    (`agents/registry.py`), não pra cada salvamento do agente."""
    unknown = [n for n in names if not tool_exists(n)]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Tools desconhecidas: {unknown}")

    faltando: dict[str, list[str]] = {}
    for name in names:
        row = get_tool(name)
        if row is None or row["kind"] != "api":
            continue
        ausentes = [d for d in required_dependencies(row["config"] or {}) if d not in declared_dependencies]
        if ausentes:
            faltando[name] = ausentes
    if faltando:
        detalhe = "; ".join(f"{tool} precisa de {', '.join(deps)}" for tool, deps in faltando.items())
        raise HTTPException(
            status_code=422,
            detail=f"Declare estes campos em dependency_fields — {detalhe}",
        )


@router.get("", response_model=list[AgentDefinitionOut])
def list_agents() -> list[dict[str, Any]]:
    return list_definitions()


@router.post("", response_model=AgentDefinitionOut, status_code=201)
def create_agent(body: AgentDefinitionIn) -> dict[str, Any]:
    if get_definition(body.agent_type) is not None:
        raise HTTPException(status_code=409, detail=f"Agente {body.agent_type!r} já existe")
    payload = body.model_dump()
    payload["dependency_fields"] = _normalize_dependency_fields(body.dependency_fields)
    _validate_tools(body.tools, {f["name"] for f in payload["dependency_fields"]})
    _validate_collection(body.knowledge_collection)
    return create_definition(**payload)


@router.get("/{agent_type}", response_model=AgentDefinitionOut)
def get_agent_definition(agent_type: str) -> dict[str, Any]:
    definition = get_definition(agent_type)
    if definition is None:
        raise HTTPException(status_code=404, detail=f"Agente {agent_type!r} não encontrado")
    return definition


@router.put("/{agent_type}", response_model=AgentDefinitionOut)
def update_agent(agent_type: str, body: AgentDefinitionUpdate) -> dict[str, Any]:
    current = get_definition(agent_type)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Agente {agent_type!r} não encontrado")

    payload = body.model_dump(exclude_unset=True)
    if "knowledge_collection" in payload:
        _validate_collection(payload["knowledge_collection"])
    if body.dependency_fields is not None:
        payload["dependency_fields"] = _normalize_dependency_fields(body.dependency_fields)
    # Valida contra o estado final: tools e dependency_fields podem vir juntos ou só um deles.
    if body.tools is not None or body.dependency_fields is not None:
        campos = payload.get("dependency_fields", current["dependency_fields"] or [])
        _validate_tools(
            body.tools if body.tools is not None else (current["tools"] or []),
            {f["name"] for f in campos},
        )
    try:
        updated = update_definition(agent_type, **payload)
    except DefinitionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Agente {agent_type!r} não encontrado") from exc
    return updated


@router.delete("/{agent_type}", status_code=204)
def delete_agent(agent_type: str) -> None:
    definition = get_definition(agent_type)
    if definition is None:
        raise HTTPException(status_code=404, detail=f"Agente {agent_type!r} não encontrado")
    if definition["is_seed"]:
        raise HTTPException(status_code=403, detail="Agente semeado pelo sistema não pode ser removido")
    delete_definition(agent_type)


@router.get("/{agent_type}/versions", response_model=list[PromptVersionOut])
def get_prompt_versions(agent_type: str) -> list[dict[str, Any]]:
    if get_definition(agent_type) is None:
        raise HTTPException(status_code=404, detail=f"Agente {agent_type!r} não encontrado")
    return list_prompt_versions(agent_type)
