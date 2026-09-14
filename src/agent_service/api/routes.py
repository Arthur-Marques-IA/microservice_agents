"""Contrato estável de API que os demais módulos da plataforma consomem.

Fica deliberadamente separado das rotas que o AgentOS expõe automaticamente
(`/agents/{id}/runs`, etc.) — este router é o ponto único e estável que outros
serviços chamam, independente de como o agente é montado por baixo (Agno,
outro framework, etc. no futuro).
"""

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agent_service.agents.registry import UnknownAgentTypeError, get_agent, list_agent_types
from agent_service.documents.collections import COLLECTION_NAMES, add_text, search
from agent_service.observability.tracing import traced_agent_run

router = APIRouter()


class ChatRequest(BaseModel):
    agent_type: str = "conversational"
    user_id: str
    session_id: str
    message: str


class ChatResponse(BaseModel):
    agent_type: str
    session_id: str
    content: str


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/agent-types")
def agent_types() -> dict[str, list[str]]:
    return {"agent_types": list_agent_types()}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        agent = get_agent(request.agent_type)
    except UnknownAgentTypeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    run_output = await traced_agent_run(
        agent, message=request.message, user_id=request.user_id, session_id=request.session_id
    )
    return ChatResponse(
        agent_type=request.agent_type,
        session_id=request.session_id,
        content=run_output.content or "",
    )


class AddTextRequest(BaseModel):
    text: str
    name: str | None = None
    metadata: dict[str, Any] | None = None


class SearchResult(BaseModel):
    content: str
    metadata: dict[str, Any] | None = None


@router.get("/collections")
def collections() -> dict[str, list[str]]:
    return {"collections": COLLECTION_NAMES}


@router.post("/collections/{collection_name}/documents", status_code=201)
async def ingest_text(collection_name: str, request: AddTextRequest) -> dict[str, str]:
    if collection_name not in COLLECTION_NAMES:
        raise HTTPException(status_code=404, detail=f"Coleção desconhecida: {collection_name!r}")
    content_id = await add_text(
        collection_name, text=request.text, name=request.name, metadata=request.metadata
    )
    return {"content_id": content_id}


@router.get("/collections/{collection_name}/search", response_model=list[SearchResult])
async def search_collection(collection_name: str, query: str, limit: int = 5) -> list[SearchResult]:
    if collection_name not in COLLECTION_NAMES:
        raise HTTPException(status_code=404, detail=f"Coleção desconhecida: {collection_name!r}")
    documents = await search(collection_name, query=query, limit=limit)
    return [SearchResult(content=doc.content, metadata=doc.meta_data) for doc in documents]


@router.get("/chat/stream")
async def chat_stream(agent_type: str, user_id: str, session_id: str, message: str) -> EventSourceResponse:
    try:
        agent = get_agent(agent_type)
    except UnknownAgentTypeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def event_generator():
        async for event in agent.arun(
            message, user_id=user_id, session_id=session_id, stream=True, stream_events=False
        ):
            content = getattr(event, "content", None)
            if content:
                yield {"event": "message", "data": json.dumps({"content": content})}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_generator())
