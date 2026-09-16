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

from agent_service.agents.store import (
    DefinitionNotFoundError,
    create_definition,
    delete_definition,
    get_definition,
    list_definitions,
    list_prompt_versions,
    update_definition,
)
from agent_service.tools.registry import tool_exists

router = APIRouter(prefix="/agents", tags=["agents"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class AgentDefinitionIn(BaseModel):
    agent_type: str = Field(..., description="Slug estável, usado como agent_id no /chat")
    name: str
    instructions: list[str] = Field(..., min_length=1)
    tools: list[str] = []
    model_provider: str | None = None
    model_id: str | None = None
    memory_backend: Literal["common", "mem0"] = "common"
    num_history_runs: int = 10

    @field_validator("agent_type")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("agent_type deve ser um slug: letras minúsculas, números, '-' ou '_'")
        return v


class AgentDefinitionUpdate(BaseModel):
    name: str | None = None
    instructions: list[str] | None = Field(default=None, min_length=1)
    tools: list[str] | None = None
    model_provider: str | None = None
    model_id: str | None = None
    memory_backend: Literal["common", "mem0"] | None = None
    num_history_runs: int | None = None


class AgentDefinitionOut(BaseModel):
    agent_type: str
    name: str
    instructions: list[str]
    tools: list[str]
    model_provider: str | None
    model_id: str | None
    memory_backend: str
    num_history_runs: int
    is_seed: bool
    prompt_version: int
    created_at: datetime
    updated_at: datetime


class PromptVersionOut(BaseModel):
    version: int
    instructions: list[str]
    created_at: datetime


def _validate_tools(names: list[str]) -> None:
    """Só confere que os nomes existem em `tool_definitions` — construir de
    fato (instanciar toolkit, compilar código Python...) fica pra hora do
    `/chat` (`agents/registry.py`), não pra cada salvamento do agente."""
    unknown = [n for n in names if not tool_exists(n)]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Tools desconhecidas: {unknown}")


@router.get("", response_model=list[AgentDefinitionOut])
def list_agents() -> list[dict[str, Any]]:
    return list_definitions()


@router.post("", response_model=AgentDefinitionOut, status_code=201)
def create_agent(body: AgentDefinitionIn) -> dict[str, Any]:
    if get_definition(body.agent_type) is not None:
        raise HTTPException(status_code=409, detail=f"Agente {body.agent_type!r} já existe")
    _validate_tools(body.tools)
    return create_definition(**body.model_dump())


@router.get("/{agent_type}", response_model=AgentDefinitionOut)
def get_agent_definition(agent_type: str) -> dict[str, Any]:
    definition = get_definition(agent_type)
    if definition is None:
        raise HTTPException(status_code=404, detail=f"Agente {agent_type!r} não encontrado")
    return definition


@router.put("/{agent_type}", response_model=AgentDefinitionOut)
def update_agent(agent_type: str, body: AgentDefinitionUpdate) -> dict[str, Any]:
    if body.tools is not None:
        _validate_tools(body.tools)
    try:
        updated = update_definition(agent_type, **body.model_dump(exclude_unset=True))
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
