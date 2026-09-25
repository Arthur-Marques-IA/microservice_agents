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
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agno.run.agent import RunEvent

from agent_service.agents.attachments import AttachmentError, AttachmentIn, build_media
from agent_service.agents.dependency_fields import DependencyValidationError, validate_dependencies
from agent_service.agents.registry import UnknownAgentTypeError, get_agent_with_definition, list_agent_types
from agent_service.config import get_settings
from agent_service.documents.collections import EmbedderError
from agent_service.observability.tracing import RUN_FAILED, RunContext, traced_run_events
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
    """Id do trace do run — o mesmo no trace store local e no Langfuse, se ligado."""
    agent_version: int | None = None
    """Versão da configuração inteira que respondeu (`GET /agents/{t}/revisions`)."""
    config_hash: str | None = None


def _resolve(request: ChatRequest, endpoint: str) -> tuple[Agent, RunContext]:
    """Monta o agente e o contexto do run. Faz I/O síncrono no Postgres (definição,
    nota de feedback, uma consulta por tool): chame via `run_in_threadpool`, nunca
    direto numa rota `async` — travaria o event loop do worker inteiro."""
    try:
        agent, definition = get_agent_with_definition(request.agent_type)
    except UnknownAgentTypeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ToolBuildError, UnknownToolError) as exc:
        # Uma das tools do agente não pôde ser montada (config inválida, dependência
        # opcional ausente, tool Python desligada...) — problema nosso, não de quem chama.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except EmbedderError as exc:
        # A collection do agente perdeu a credencial do embedder: configuração do
        # serviço, não da chamada.
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
        agent_version=definition.get("agent_version"),
        config_hash=definition.get("config_hash"),
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
    """Aberta de propósito: é o healthcheck do container e de qualquer load
    balancer na frente. Só responde se o processo está de pé — não checa banco:
    com o Postgres fora, reiniciar o container não resolveria nada.

    `auth` aparece aqui porque é a primeira coisa que alguém precisa saber ao
    olhar um serviço que não conhece, e não é segredo: quem não tem chave
    descobre no primeiro request de qualquer jeito."""
    from agent_service.api.auth import auth_enabled

    return {"status": "ok", "auth": "enabled" if auth_enabled() else "disabled"}


@router.get("/agent-types")
def agent_types() -> dict[str, list[str]]:
    return {"agent_types": list_agent_types()}


def _check_input_size(text: str, field: str) -> None:
    """Texto de entrada tem teto. Sem ele, o documento vai inteiro para o modelo e
    a falha aparece como um erro do provedor, sem dizer o que foi grande demais.
    O limite é em caracteres, não em tokens — é o que dá para medir aqui."""
    limit = get_settings().max_input_chars
    if len(text) > limit:
        raise HTTPException(
            status_code=422,
            detail=f"{field} tem {len(text)} caracteres e o limite é {limit} "
            f"(MAX_INPUT_CHARS). Resuma o texto, ou mande o conteúdo como anexo.",
        )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    _check_input_size(request.message, "message")
    agent, run = await run_in_threadpool(_resolve, request, "chat")

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
        trace_id=run.trace_id,
        agent_version=run.agent_version,
        config_hash=run.config_hash,
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
    """Id da execução — serve de id da decisão na auditoria de quem chama."""
    trace_id: str | None = None
    agent_version: int | None = None
    """Versão da configuração inteira que decidiu (`GET /agents/{t}/revisions`)."""
    config_hash: str | None = None


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """One-shot: sem sessão/histórico — devolve o `document` analisado como
    objeto estruturado (`response_schema` do agente), não texto."""
    _check_input_size(request.document, "document")
    try:
        # I/O síncrono no Postgres — fora do event loop (ver `_resolve`).
        agent, definition = await run_in_threadpool(get_agent_with_definition, request.agent_type)
    except UnknownAgentTypeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ToolBuildError, UnknownToolError, *EmbedderError) as exc:
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
        agent_version=definition.get("agent_version"),
        config_hash=definition.get("config_hash"),
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
        # Dizer o que veio no lugar: com response_schema aninhado a saída inválida
        # fica mais comum, e "não devolveu saída válida" sozinho não ajuda a achar
        # se o modelo respondeu texto, devolveu vazio ou errou um campo.
        recebido = repr(final_content)
        if len(recebido) > 500:
            recebido = recebido[:500] + "… (truncado)"
        raise HTTPException(
            status_code=502,
            detail=f"O agente não devolveu uma saída estruturada válida "
            f"(veio {type(final_content).__name__}): {recebido}",
        )

    return AnalyzeResponse(
        agent_type=request.agent_type,
        result=final_content.model_dump(mode="json"),
        run_id=run.run_id,
        trace_id=run.trace_id,
        agent_version=run.agent_version,
        config_hash=run.config_hash,
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
    agent, run = await run_in_threadpool(_resolve, request, "chat.stream")
    trace_id = run.trace_id

    async def event_generator():
        yield {"event": "run", "data": json.dumps(
                {
                    "run_id": run.run_id,
                    "trace_id": trace_id,
                    "agent_version": run.agent_version,
                    "config_hash": run.config_hash,
                }
            )}
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
