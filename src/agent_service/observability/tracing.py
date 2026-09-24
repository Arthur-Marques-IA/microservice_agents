"""Registro das execuções: trace store local sempre, Langfuse opcional.

Toda execução passa por `traced_run_events()` e é gravada no trace store local
(`run_store.py`, no Postgres do serviço) — é o que alimenta `kuro runs` e as
rotas `/observability/*`, com ou sem Langfuse.

O Langfuse é um exportador adicional, para quem quer a análise profunda: só é
importado com `LANGFUSE_ENABLED=true` e o extra `[observability]` instalado.
Ligado, `configure_tracing()` (startup, ver `main.py`) cria o cliente do Langfuse e
liga o `AgnoInstrumentor` (OpenInference): cada execução do Agno vira spans
OpenTelemetry — o run do agente, cada chamada ao modelo (prompt, resposta,
tokens; o Langfuse calcula o custo) e cada tool call. O exportador do SDK
envia os spans em lote, em background, sem atrasar a resposta.

`traced_run_events()` envolve cada run de `/chat` e `/chat/stream` numa
observação raiz com usuário, sessão, agente e versão do prompt. O `run_id` do
Agno é gerado aqui, antes do run, e o trace usa um id derivado dele
(`trace_id_for_run`) — assim qualquer resposta, inclusive as reidratadas do
histórico, aponta para o próprio trace e pode receber feedback (`score_run`).

Sem `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` (ou com `LANGFUSE_ENABLED=false`)
o exportador vira no-op; o registro local continua.
"""

import asyncio
import logging
import time
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import TYPE_CHECKING, Any, AsyncIterator
from uuid import uuid4

from agno.agent import Agent
from agno.run.agent import RunEvent, RunOutputEvent

from agent_service.config import get_settings
from agent_service.tools.context import set_dependencies

if TYPE_CHECKING:
    from langfuse import Langfuse

logger = logging.getLogger(__name__)

FEEDBACK = "feedback"
RUN_FAILED = "Falha ao executar o agente."
RUN_INTERRUPTED = "Execução interrompida antes de terminar (cliente desconectou ou cancelou)."
PROJECT_LOOKUP_RETRY_SECONDS = 60

_client: "Langfuse | None" = None
_project_url: str | None = None
_project_lookup_failed_at: float | None = None
_END = object()


@dataclass(frozen=True)
class RunContext:
    """Uma execução de agente e o que o trace precisa saber dela."""

    endpoint: str
    agent_type: str
    agent_name: str
    prompt_version: int
    user_id: str
    session_id: str
    message: str
    dependencies: dict[str, Any] | None = None
    # Mídia anexada (objetos `agno.media` já prontos — ver `agents/attachments.py`).
    images: tuple[Any, ...] = ()
    audio: tuple[Any, ...] = ()
    videos: tuple[Any, ...] = ()
    files: tuple[Any, ...] = ()
    run_id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def trace_id(self) -> str:
        return trace_id_for_run(self.run_id)

    @property
    def attachment_counts(self) -> dict[str, int]:
        """Quantos anexos de cada tipo — vai pro Langfuse no lugar do conteúdo."""
        counts = {
            "images": len(self.images),
            "audio": len(self.audio),
            "videos": len(self.videos),
            "files": len(self.files),
        }
        return {k: v for k, v in counts.items() if v}


def trace_id_for_run(run_id: str) -> str:
    """Id do trace para um `run_id` do Agno — determinístico.

    Mesma derivação de `Langfuse.create_trace_id(seed=...)`, sem importar o SDK:
    o id bate com o do Langfuse quando ele está ligado."""
    return sha256(run_id.encode("utf-8")).digest()[:16].hex()


def configure_tracing() -> None:
    global _client
    if _client is not None:
        return
    settings = get_settings()
    if not settings.langfuse_enabled:
        logger.info("Langfuse desligado (LANGFUSE_ENABLED=false): runs só no trace store local.")
        return
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.warning("LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY ausentes: runs só no trace store local.")
        return

    try:
        from langfuse import Langfuse
        from openinference.instrumentation.agno import AgnoInstrumentor
        from opentelemetry import trace as otel_trace
    except ImportError:
        logger.warning(
            "LANGFUSE_ENABLED=true, mas o extra `observability` não está instalado "
            "(uv sync --extra observability): runs só no trace store local."
        )
        return

    _client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
        environment=settings.langfuse_environment,
        timeout=settings.langfuse_timeout_seconds,
    )
    # O Langfuse registra o TracerProvider global; o instrumentor do Agno publica nele.
    AgnoInstrumentor().instrument(tracer_provider=otel_trace.get_tracer_provider())


def get_langfuse() -> "Langfuse | None":
    return _client


def project_url() -> str | None:
    """Projeto na UI do Langfuse (links do console), ou `None` se indisponível."""
    global _project_url, _project_lookup_failed_at
    client = _client
    if client is None:
        return None
    if _project_url is not None:
        return _project_url

    settings = get_settings()
    project_id = settings.langfuse_project_id
    if not project_id:
        # Sem LANGFUSE_PROJECT_ID, pergunta à API — mas sem martelar um Langfuse fora do ar.
        failed_at = _project_lookup_failed_at
        if failed_at is not None and time.monotonic() - failed_at < PROJECT_LOOKUP_RETRY_SECONDS:
            return None
        try:
            projects = client.api.projects.get()
            project_id = projects.data[0].id if projects.data else None
        except Exception:
            logger.warning("Não foi possível descobrir o projeto do Langfuse", exc_info=True)
        if not project_id:
            _project_lookup_failed_at = time.monotonic()
            return None

    base_url = (settings.langfuse_public_url or settings.langfuse_base_url).rstrip("/")
    _project_url = f"{base_url}/project/{project_id}"
    return _project_url


def _agent_events(agent: Agent, run: RunContext) -> AsyncIterator[RunOutputEvent]:
    # Além de irem para o contexto do prompt, as dependências ficam disponíveis para
    # as tools com parâmetros `source="dependency"` (ver tools/context.py).
    set_dependencies(run.dependencies)
    return agent.arun(
        run.message,
        user_id=run.user_id,
        session_id=run.session_id,
        run_id=run.run_id,
        stream=True,
        stream_events=True,
        dependencies=run.dependencies,
        add_dependencies_to_context=True if run.dependencies else None,
        images=list(run.images) or None,
        audio=list(run.audio) or None,
        videos=list(run.videos) or None,
        files=list(run.files) or None,
    )


def _utc(timestamp: float | None) -> datetime | None:
    return datetime.fromtimestamp(timestamp, timezone.utc) if timestamp else None


def _ms(seconds: float | None) -> float | None:
    return round(seconds * 1000, 1) if seconds else None


def _model_spans(metrics: Any, started_at: datetime) -> list[Any]:
    """Uma span por modelo chamado, das métricas agregadas do Agno (`RunMetrics.details`)."""
    from agent_service.observability.run_store import SpanRecord

    spans = []
    for model_type, entries in (getattr(metrics, "details", None) or {}).items():
        for entry in entries or []:
            provider = getattr(entry, "provider", "") or "model"
            spans.append(
                SpanRecord(
                    type="GENERATION",
                    name=f"{provider}.{model_type}",
                    started_at=started_at,
                    model=getattr(entry, "id", None) or None,
                    input_tokens=getattr(entry, "input_tokens", 0) or 0,
                    output_tokens=getattr(entry, "output_tokens", 0) or 0,
                    total_tokens=getattr(entry, "total_tokens", 0) or 0,
                    cost_usd=getattr(entry, "cost", None),
                    latency_ms=_ms(getattr(entry, "duration", None)),
                )
            )
    return spans


def _tool_span(event: Any, now: datetime) -> Any:
    from agent_service.observability.run_store import SpanRecord

    tool = event.tool
    tool_metrics = getattr(tool, "metrics", None)
    failed = event.event == RunEvent.tool_call_error.value or bool(getattr(tool, "tool_call_error", False))
    return SpanRecord(
        type="TOOL",
        name=getattr(tool, "tool_name", None) or "tool",
        started_at=_utc(getattr(tool_metrics, "start_time", None)) or now,
        ended_at=_utc(getattr(tool_metrics, "end_time", None)),
        level="ERROR" if failed else "DEFAULT",
        status_message=getattr(event, "error", None) if failed else None,
        input=getattr(tool, "tool_args", None),
        output=getattr(tool, "result", None),
        latency_ms=_ms(getattr(tool_metrics, "duration", None)),
    )


async def _recorded_events(agent: Agent, run: RunContext) -> AsyncIterator[RunOutputEvent]:
    """Eventos do run, gravados no trace store local ao terminar — sempre com status
    terminal: sucesso, erro ou interrompido (cliente saiu / cancelamento)."""
    from agent_service.observability import run_store

    record = run_store.RunRecord(
        run_id=run.run_id,
        trace_id=run.trace_id,
        agent_type=run.agent_type,
        agent_name=run.agent_name,
        prompt_version=run.prompt_version,
        endpoint=run.endpoint,
        user_id=run.user_id,
        session_id=run.session_id,
        message=run.message,
        started_at=datetime.now(timezone.utc),
        input={
            "message": run.message,
            "dependencies": run.dependencies,
            **({"attachments": run.attachment_counts} if run.attachment_counts else {}),
        },
    )
    chunks: list[str] = []
    final_content: str | None = None
    try:
        async for event in _agent_events(agent, run):
            if event.event == RunEvent.run_content.value and isinstance(event.content, str):
                chunks.append(event.content)
            elif event.event == RunEvent.run_completed.value:
                if isinstance(event.content, str):
                    final_content = event.content
                elif hasattr(event.content, "model_dump_json"):
                    final_content = event.content.model_dump_json()
                metrics = getattr(event, "metrics", None)
                if metrics is not None:
                    record.input_tokens = metrics.input_tokens or 0
                    record.output_tokens = metrics.output_tokens or 0
                    record.total_tokens = metrics.total_tokens or 0
                    record.cost_usd = metrics.cost
                    record.spans.extend(_model_spans(metrics, record.started_at))
            elif event.event == RunEvent.run_error.value:
                record.status = "error"
                record.status_message = event.content or RUN_FAILED
            elif event.event in (RunEvent.tool_call_completed.value, RunEvent.tool_call_error.value):
                if getattr(event, "tool", None) is not None:
                    record.spans.append(_tool_span(event, datetime.now(timezone.utc)))
            if record.model is None and isinstance(getattr(event, "model", None), str):
                record.model = event.model or None
            yield event
    except (asyncio.CancelledError, GeneratorExit):
        record.status = "interrupted"
        record.status_message = RUN_INTERRUPTED
        raise
    except Exception as exc:
        record.status = "error"
        record.status_message = str(exc) or type(exc).__name__
        raise
    finally:
        output = final_content if final_content is not None else "".join(chunks)
        record.output = output or None
        if record.model is None:
            record.model = next((span.model for span in record.spans if span.model), None)
        record.ended_at = datetime.now(timezone.utc)
        run_store.record_run(record)


async def traced_run_events(agent: Agent, run: RunContext) -> AsyncIterator[RunOutputEvent]:
    """Eventos do run, registrados no trace store local (e no Langfuse, se ligado).
    Consuma dentro de `contextlib.aclosing`.

    Com o Langfuse, o run executa numa task própria que alimenta uma fila: o
    contexto do OpenTelemetry (a observação raiz) é aberto e fechado dentro dessa
    task, em vez de atravessar os `yield` deste generator — o que quebraria a
    árvore de spans quando o consumidor (ex. o SSE) intercala seu próprio código.
    """
    client = _client
    if client is None:
        async with aclosing(_recorded_events(agent, run)) as events:
            async for event in events:
                yield event
        return

    queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=64)
    producer = asyncio.create_task(_produce(client, agent, run, queue))
    try:
        while True:
            item = await queue.get()
            if item is _END:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        # Consumidor saiu antes do fim (cliente desconectou): cancela o run, que
        # fecha a observação raiz como interrompida.
        if not producer.done():
            producer.cancel()


async def _produce(client: "Langfuse", agent: Agent, run: RunContext, queue: asyncio.Queue[Any]) -> None:
    from langfuse import propagate_attributes

    chunks: list[str] = []
    final_content: str | None = None
    error: str | None = None
    try:
        with (
            propagate_attributes(
                user_id=run.user_id,
                session_id=run.session_id,
                trace_name=run.agent_type,
                tags=[run.agent_type, run.endpoint],
                version=f"prompt-v{run.prompt_version}",
                metadata={
                    "agent_type": run.agent_type,
                    "agent_name": run.agent_name,
                    "prompt_version": str(run.prompt_version),
                    "endpoint": run.endpoint,
                    "run_id": run.run_id,
                },
            ),
            client.start_as_current_observation(
                trace_context={"trace_id": run.trace_id},
                name=run.endpoint,
                input={
                    "message": run.message,
                    "dependencies": run.dependencies,
                    **({"attachments": run.attachment_counts} if run.attachment_counts else {}),
                },
            ) as root,
        ):
            try:
                async with aclosing(_recorded_events(agent, run)) as events:
                    async for event in events:
                        if event.event == RunEvent.run_content.value and isinstance(event.content, str):
                            chunks.append(event.content)
                        elif event.event == RunEvent.run_completed.value and isinstance(event.content, str):
                            final_content = event.content
                        elif event.event == RunEvent.run_error.value:
                            error = event.content or RUN_FAILED
                        await queue.put(event)
            except asyncio.CancelledError:
                root.update(output="".join(chunks) or None, level="WARNING", status_message=RUN_INTERRUPTED)
                raise
            except Exception as exc:
                root.update(level="ERROR", status_message=str(exc) or type(exc).__name__)
                raise

            output = final_content if final_content is not None else "".join(chunks)
            if error:
                root.update(output=output or None, level="ERROR", status_message=error)
            else:
                root.update(output=output)
    except asyncio.CancelledError:
        # Cancelamento vindo de fora (shutdown do servidor): sinaliza o fim para
        # não deixar o consumidor esperando um evento que não vem mais.
        if not queue.full():
            queue.put_nowait(_END)
        raise
    except Exception as exc:
        await queue.put(exc)
        return
    await queue.put(_END)


def score_run(
    *,
    run_id: str,
    name: str,
    value: float,
    comment: str | None = None,
    user_id: str | None = None,
) -> str:
    """Registra um score do run no trace store local (e no Langfuse, se ligado). Devolve o `trace_id`."""
    from agent_service.observability import run_store

    trace_id = trace_id_for_run(run_id)
    run_store.save_score(run_id=run_id, name=name, value=value, comment=comment, user_id=user_id)
    client = _client
    if client is not None:
        client.create_score(
            trace_id=trace_id,
            name=name,
            value=value,
            data_type="BOOLEAN" if name == FEEDBACK else "NUMERIC",
            comment=comment,
            # Um score por trace/nome/usuário: votar de novo substitui o voto anterior.
            score_id=trace_id_for_run(f"{trace_id}:{name}:{user_id}") if user_id else None,
            metadata={"user_id": user_id} if user_id else None,
        )
    return trace_id
