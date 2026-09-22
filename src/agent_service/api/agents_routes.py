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
from agent_service.agents.feedback import merge_feedback
from agent_service.agents.response_model import (
    RESPONSE_TYPES,
    ITEM_TYPES,
    ResponseSchemaError,
    validate_response_schema,
)
from agent_service.agents.registry import get_agent_with_definition
from agent_service.agents.store import (
    DefinitionNotFoundError,
    create_definition,
    delete_definition,
    get_definition,
    get_feedback_note,
    list_definitions,
    list_prompt_versions,
    update_definition,
)
from agent_service.documents.collections import collection_exists
from agent_service.tools.api_tool import required_dependencies
from agent_service.tools.registry import tool_exists
from agent_service.tools.store import get_tool

AgentKind = Literal["conversational", "analysis"]

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


ResponseFieldType = Literal["string", "integer", "number", "boolean", "object", "array"]
ItemType = Literal["string", "integer", "number", "boolean", "object"]


class ResponseItemIn(BaseModel):
    """O elemento de um `array`. `fields` é obrigatório quando `type="object"`."""

    type: ItemType = "string"
    fields: "list[ResponseFieldIn] | None" = None


class ResponseFieldIn(BaseModel):
    """Campo de `response_schema`. Folha tem a mesma forma de `dependency_fields`;
    `object` pede `fields` e `array` pede `items` (ver agents/response_model.py)."""

    name: str
    type: ResponseFieldType = "string"
    label: str | None = None
    description: str | None = None
    required: bool = False
    default: Any = None
    fields: "list[ResponseFieldIn] | None" = None
    items: ResponseItemIn | None = None


class ResponseItemOut(BaseModel):
    type: ItemType
    fields: "list[ResponseFieldOut] | None" = None


class ResponseFieldOut(BaseModel):
    name: str
    type: ResponseFieldType
    label: str
    description: str
    required: bool
    default: Any = None
    fields: "list[ResponseFieldOut] | None" = None
    items: ResponseItemOut | None = None


for _model in (ResponseItemIn, ResponseFieldIn, ResponseItemOut, ResponseFieldOut):
    _model.model_rebuild()


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
    kind: AgentKind = "conversational"
    response_schema: list[ResponseFieldIn] = Field(
        default=[],
        description="Só para kind='analysis': campos da saída estruturada. Folhas iguais a "
        "dependency_fields, mais 'object' (com fields) e 'array' (com items).",
    )

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
    kind: AgentKind | None = None
    response_schema: list[ResponseFieldIn] | None = None

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
    kind: AgentKind
    response_schema: list[ResponseFieldOut]
    is_seed: bool
    prompt_version: int
    created_at: datetime
    updated_at: datetime


class FeedbackIn(BaseModel):
    session_id: str
    feedback: str


class FeedbackOut(BaseModel):
    agent_type: str
    content: str
    updated_at: datetime


def _normalize_dependency_fields(fields: list[DependencyFieldIn]) -> list[dict[str, Any]]:
    try:
        return validate_field_specs([f.model_dump() for f in fields])
    except DependencyFieldSpecError as exc:
        raise ValueError(str(exc)) from exc


def _normalize_response_schema(fields: list[ResponseFieldIn]) -> list[dict[str, Any]]:
    """Valida aqui, e não num `field_validator`: as regras dos tipos compostos
    (`fields` obrigatório em object, `items` em array, profundidade) rendem
    mensagens específicas, e 422 com a explicação é mais útil que um erro de
    schema do pydantic."""
    try:
        return validate_response_schema([f.model_dump(exclude_none=True) for f in fields])
    except ResponseSchemaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class PromptVersionOut(BaseModel):
    version: int
    instructions: list[str]
    created_at: datetime


# Campos que existem para agentes conversacionais e não fazem nada num agente
# `analysis`: ele é one-shot, sem sessão, sem histórico e sem memória
# (`agents/base.py`). Aceitá-los calado deixa quem opera achando que configurou algo.
_INERTES_EM_ANALYSIS = {
    "num_history_runs": "analysis é one-shot: não há histórico para reaproveitar",
    "memory_backend": "analysis não usa memória de longo prazo (nem a do Agno, nem o mem0)",
}


def _validate_kind(kind: str, response_schema: list[dict[str, Any]]) -> None:
    if kind == "analysis" and not response_schema:
        raise HTTPException(status_code=422, detail="kind='analysis' precisa de response_schema (ao menos 1 campo)")
    if kind == "conversational" and response_schema:
        raise HTTPException(
            status_code=422, detail="response_schema só se aplica a kind='analysis' (deixe [] para conversational)"
        )


def _default_de(campo: str) -> Any:
    return AgentDefinitionIn.model_fields[campo].default


def _validate_inert_fields(kind: str, body: BaseModel) -> None:
    """Recusa campo inerte que veio com valor diferente do padrão.

    Dois critérios juntos, e os dois são necessários. `model_fields_set` porque
    um agente salvo carrega `num_history_runs=10` por default e cobrar isso faria
    um `PUT` de instructions falhar por um campo que ninguém escreveu. E o valor
    ter de diferir do padrão porque `kuro agents get --editable` devolve *todos*
    os campos editáveis — o fluxo documentado `get --editable > f.json && apply
    -f f.json` reenviaria os defaults e quebraria em todo agente analista.

    O que sobra é o que interessa: alguém configurou de fato algo que não vai
    surtir efeito."""
    if kind != "analysis":
        return
    configurados = [
        campo
        for campo in body.model_fields_set
        if campo in _INERTES_EM_ANALYSIS and getattr(body, campo) != _default_de(campo)
    ]
    if configurados:
        detalhe = "; ".join(f"{campo} ({_INERTES_EM_ANALYSIS[campo]})" for campo in sorted(configurados))
        raise HTTPException(
            status_code=422,
            detail=f"Estes campos não têm efeito em kind='analysis' — tire-os da requisição: {detalhe}",
        )


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
    payload["response_schema"] = _normalize_response_schema(body.response_schema)
    _validate_tools(body.tools, {f["name"] for f in payload["dependency_fields"]})
    _validate_collection(body.knowledge_collection)
    _validate_kind(body.kind, payload["response_schema"])
    _validate_inert_fields(body.kind, body)
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
    if body.response_schema is not None:
        payload["response_schema"] = _normalize_response_schema(body.response_schema)
    # Valida contra o estado final: tools e dependency_fields podem vir juntos ou só um deles.
    if body.tools is not None or body.dependency_fields is not None:
        campos = payload.get("dependency_fields", current["dependency_fields"] or [])
        _validate_tools(
            body.tools if body.tools is not None else (current["tools"] or []),
            {f["name"] for f in campos},
        )
    if body.kind is not None or body.response_schema is not None:
        _validate_kind(
            payload.get("kind", current["kind"]),
            payload.get("response_schema", current["response_schema"] or []),
        )
    _validate_inert_fields(payload.get("kind", current["kind"]), body)
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


def _transcript(agent_type: str, session_id: str) -> str:
    """Últimas mensagens da sessão, direto do storage do próprio agente
    (`Agent.get_chat_history` do Agno) — sem reimplementar leitura de sessão."""
    agent, _ = get_agent_with_definition(agent_type)
    try:
        messages = agent.get_chat_history(session_id=session_id, last_n_runs=10)
    except Exception:  # noqa: BLE001 - o Agno levanta Exception("Session not found") pra sessão inexistente
        messages = []
    lines = [f"{m.role}: {m.content}" for m in messages if m.content]
    if not lines:
        raise HTTPException(
            status_code=422, detail=f"Sessão {session_id!r} não tem histórico para {agent_type!r}."
        )
    return "\n".join(lines)


@router.post("/{agent_type}/feedback", response_model=FeedbackOut)
def send_feedback(agent_type: str, body: FeedbackIn) -> dict[str, Any]:
    """Mescla um feedback textual sobre uma conversa numa nota de comportamento
    persistente — `agents/registry.py` concatena essa nota nas instructions do
    agente a partir da próxima chamada (sem virar uma prompt_version nova)."""
    definition = get_definition(agent_type)
    if definition is None:
        raise HTTPException(status_code=404, detail=f"Agente {agent_type!r} não encontrado")
    _reject_feedback_on_analysis(definition)
    transcript = _transcript(agent_type, body.session_id)
    merge_feedback(agent_type, feedback=body.feedback, transcript=transcript)
    note = get_feedback_note(agent_type)
    assert note is not None
    return note


def _reject_feedback_on_analysis(definition: dict[str, Any]) -> None:
    """A nota de feedback só entra nas instructions de agente conversacional
    (`agents/registry.py`). Aceitar feedback num agente `analysis` gravaria uma
    nota que nunca seria aplicada — silêncio pior que erro."""
    if (definition.get("kind") or "conversational") == "analysis":
        raise HTTPException(
            status_code=422,
            detail=f"Agente {definition['agent_type']!r} é kind='analysis' e não usa nota de feedback "
            "(ela só orienta agentes conversacionais). Ajuste as instructions do agente.",
        )


@router.get("/{agent_type}/feedback", response_model=FeedbackOut)
def get_feedback(agent_type: str) -> dict[str, Any]:
    definition = get_definition(agent_type)
    if definition is None:
        raise HTTPException(status_code=404, detail=f"Agente {agent_type!r} não encontrado")
    _reject_feedback_on_analysis(definition)
    note = get_feedback_note(agent_type)
    if note is None:
        raise HTTPException(status_code=404, detail=f"Nenhum feedback registrado ainda para {agent_type!r}.")
    return note
