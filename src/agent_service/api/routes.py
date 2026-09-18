"""Contrato estável de API que os demais módulos da plataforma consomem.

Fica deliberadamente separado das rotas que o AgentOS expõe automaticamente
(`/agents/{id}/runs`, etc.) — este router é o ponto único e estável que outros
serviços chamam, independente de como o agente é montado por baixo (Agno,
outro framework, etc. no futuro).

Collections de documentos ficam em `api/collections_routes.py`.
"""

import json
import logging
import uuid
from contextlib import aclosing
from typing import Any

from agno.agent import Agent
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agno.run.agent import RunEvent

from agent_service.agents.attachments import AttachmentError, AttachmentIn, build_media
from agent_service.agents.dependency_fields import DependencyValidationError, validate_dependencies
from agent_service.agents.registry import UnknownAgentTypeError, get_agent_with_definition, list_agent_types
from agent_service.observability.tracing import RUN_FAILED, RunContext, get_langfuse, traced_run_events
from agent_service.tools.registry import ToolBuildError, UnknownToolError

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    agent_type: str = "conversational"
    user_id: str
    session_id: str
    message: str
    dependencies: dict[str, Any] | None = None
    """Metadados opcionais (ex: cpf, nome) injetados como contexto estruturado
    no prompt — ver a aba Integração dos agentes no frontend para exemplos."""
    attachments: list[AttachmentIn] = []
    """Imagem, áudio, vídeo ou arquivo (PDF etc.) em base64 (`content_base64`)
    ou por `url`, com `mime_type`/`filename` — o modelo do agente precisa
    suportar o tipo (ex.: Gemini)."""


class ChatResponse(BaseModel):
    agent_type: str
    session_id: str
    content: str
    run_id: str
    """Id do run — use em `POST /observability/scores` para enviar feedback."""
    trace_id: str | None = None
    """Trace no Langfuse (`None` com a observabilidade desligada)."""


def _resolve(request: ChatRequest, endpoint: str) -> tuple[Agent, RunContext]:
    try:
        agent, definition = get_agent_with_definition(request.agent_type)
    except UnknownAgentTypeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ToolBuildError, UnknownToolError) as exc:
        # Uma das tools do agente não pôde ser montada (config inválida, dependência
        # opcional ausente, tool Python desligada...) — problema nosso, não de quem chama.
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        dependencies = validate_dependencies(definition.get("dependency_fields"), request.dependencies)
    except DependencyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    media = _build_media_or_422(request.attachments)

    run = RunContext(
        endpoint=endpoint,
        agent_type=request.agent_type,
        agent_name=definition["name"],
        prompt_version=definition["prompt_version"],
        user_id=request.user_id,
        session_id=request.session_id,
        message=request.message,
        dependencies=dependencies,
        images=tuple(media["images"]),
        audio=tuple(media["audio"]),
        videos=tuple(media["videos"]),
        files=tuple(media["files"]),
    )
    return agent, run


def _build_media_or_422(attachments: list[AttachmentIn]) -> dict[str, list[Any]]:
    try:
        return build_media(attachments)
    except AttachmentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/agent-types")
def agent_types() -> dict[str, list[str]]:
    return {"agent_types": list_agent_types()}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    agent, run = _resolve(request, "chat")

    chunks: list[str] = []
    final_content: str | None = None
    async with aclosing(traced_run_events(agent, run)) as events:
        async for event in events:
            if event.event == RunEvent.run_content.value and isinstance(event.content, str):
                chunks.append(event.content)
            elif event.event == RunEvent.run_completed.value and isinstance(event.content, str):
                final_content = event.content
            elif event.event == RunEvent.run_error.value:
                raise HTTPException(status_code=502, detail=event.content or RUN_FAILED)

    return ChatResponse(
        agent_type=request.agent_type,
        session_id=request.session_id,
        content=final_content if final_content is not None else "".join(chunks),
        run_id=run.run_id,
        trace_id=run.trace_id if get_langfuse() is not None else None,
    )


class AnalyzeRequest(BaseModel):
    agent_type: str
    document: str
    dependencies: dict[str, Any] | None = None
    attachments: list[AttachmentIn] = []
    """Mesmo formato do `/chat` — ex.: um PDF direto em vez de texto extraído
    (nesse caso `document` pode ser só uma instrução curta, como 'veja o anexo')."""


class AnalyzeResponse(BaseModel):
    agent_type: str
    result: dict[str, Any]
    """Saída validada contra o `response_schema` do agente."""
    run_id: str
    trace_id: str | None = None


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """One-shot: sem sessão/histórico — devolve o `document` analisado como
    objeto estruturado (`response_schema` do agente), não texto."""
    try:
        agent, definition = get_agent_with_definition(request.agent_type)
    except UnknownAgentTypeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ToolBuildError, UnknownToolError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if (definition.get("kind") or "conversational") != "analysis":
        raise HTTPException(
            status_code=422, detail=f"Agente {request.agent_type!r} não é do tipo 'analysis' (veja GET /agents)."
        )

    try:
        dependencies = validate_dependencies(definition.get("dependency_fields"), request.dependencies)
    except DependencyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    media = _build_media_or_422(request.attachments)

    run = RunContext(
        endpoint="analyze",
        agent_type=request.agent_type,
        agent_name=definition["name"],
        prompt_version=definition["prompt_version"],
        user_id="analysis",
        session_id=f"analyze-{uuid.uuid4().hex}",
        message=request.document,
        dependencies=dependencies,
        images=tuple(media["images"]),
        audio=tuple(media["audio"]),
        videos=tuple(media["videos"]),
        files=tuple(media["files"]),
    )

    final_content: Any = None
    async with aclosing(traced_run_events(agent, run)) as events:
        async for event in events:
            if event.event == RunEvent.run_completed.value:
                final_content = event.content
            elif event.event == RunEvent.run_error.value:
                raise HTTPException(status_code=502, detail=event.content or RUN_FAILED)

    if not isinstance(final_content, BaseModel):
        raise HTTPException(status_code=502, detail="O agente não devolveu uma saída estruturada válida.")

    return AnalyzeResponse(
        agent_type=request.agent_type,
        result=final_content.model_dump(mode="json"),
        run_id=run.run_id,
        trace_id=run.trace_id if get_langfuse() is not None else None,
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> EventSourceResponse:
    """Streaming via POST (não GET): a mensagem do usuário vai no corpo, não
    na query string — evita acabar em log de acesso. `EventSource` do browser
    só faz GET, então o cliente precisa consumir isso com `fetch` + leitura
    manual do stream (ver `frontend/`), não com a API `EventSource`.

    Eventos: `run` ({run_id, trace_id}, antes de tudo), `message` ({content}, a
    cada trecho), `usage` (métricas do run), `error` ({message}) e `done`.
    """
    agent, run = _resolve(request, "chat.stream")
    trace_id = run.trace_id if get_langfuse() is not None else None

    async def event_generator():
        yield {"event": "run", "data": json.dumps({"run_id": run.run_id, "trace_id": trace_id})}
        async with aclosing(traced_run_events(agent, run)) as events:
            try:
                async for event in events:
                    if event.event == RunEvent.run_content.value and event.content:
                        yield {"event": "message", "data": json.dumps({"content": event.content})}
                    elif event.event == RunEvent.run_completed.value and event.metrics:
                        yield {"event": "usage", "data": json.dumps(event.metrics.to_dict())}
                    elif event.event == RunEvent.run_error.value:
                        yield {"event": "error", "data": json.dumps({"message": event.content or RUN_FAILED})}
            except Exception:
                logger.exception("Falha no streaming do agente %r", request.agent_type)
                yield {"event": "error", "data": json.dumps({"message": RUN_FAILED})}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_generator())
