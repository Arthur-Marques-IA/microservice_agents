"""Observabilidade com Langfuse.

`configure_tracing()` (startup, ver `main.py`) cria o cliente do Langfuse e
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
tudo vira no-op: os runs seguem normalmente, só não são rastreados.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from uuid import uuid4

from agno.agent import Agent
from agno.run.agent import RunEvent, RunOutputEvent
from langfuse import Langfuse, propagate_attributes
from openinference.instrumentation.agno import AgnoInstrumentor
from opentelemetry import trace as otel_trace

from agent_service.config import get_settings

logger = logging.getLogger(__name__)

FEEDBACK = "feedback"
RUN_FAILED = "Falha ao executar o agente."
RUN_INTERRUPTED = "Execução interrompida antes de terminar (cliente desconectou ou cancelou)."
PROJECT_LOOKUP_RETRY_SECONDS = 60

_client: Langfuse | None = None
_project_url: str | None = None
_project_lookup_failed_at: float | None = None
_END = object()


class ObservabilityDisabledError(RuntimeError):
    pass


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
    run_id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def trace_id(self) -> str:
        return trace_id_for_run(self.run_id)


def trace_id_for_run(run_id: str) -> str:
    """Id do trace no Langfuse para um `run_id` do Agno — determinístico."""
    return Langfuse.create_trace_id(seed=run_id)


def configure_tracing() -> None:
    global _client
    if _client is not None:
        return
    settings = get_settings()
    if not settings.langfuse_enabled:
        logger.info("Langfuse desligado (LANGFUSE_ENABLED=false): runs não serão rastreados.")
        return
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.warning("LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY ausentes: runs não serão rastreados.")
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


def get_langfuse() -> Langfuse | None:
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
    return agent.arun(
        run.message,
        user_id=run.user_id,
        session_id=run.session_id,
        run_id=run.run_id,
        stream=True,
        stream_events=True,
        dependencies=run.dependencies,
        add_dependencies_to_context=True if run.dependencies else None,
    )


async def traced_run_events(agent: Agent, run: RunContext) -> AsyncIterator[RunOutputEvent]:
    """Eventos do run, rastreados no Langfuse. Consuma dentro de `contextlib.aclosing`.

    O run executa numa task própria que alimenta uma fila: o contexto do
    OpenTelemetry (a observação raiz) é aberto e fechado dentro dessa task, em
    vez de atravessar os `yield` deste generator — o que quebraria a árvore de
    spans quando o consumidor (ex. o SSE) intercala seu próprio código.
    """
    client = _client
    if client is None:
        async for event in _agent_events(agent, run):
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


async def _produce(client: Langfuse, agent: Agent, run: RunContext, queue: asyncio.Queue[Any]) -> None:
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
                input={"message": run.message, "dependencies": run.dependencies},
            ) as root,
        ):
            try:
                async for event in _agent_events(agent, run):
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
    """Registra um score no trace do run. Devolve o `trace_id`."""
    client = _client
    if client is None:
        raise ObservabilityDisabledError("Langfuse não está configurado neste serviço.")
    trace_id = trace_id_for_run(run_id)
    client.create_score(
        trace_id=trace_id,
        name=name,
        value=value,
        data_type="BOOLEAN" if name == FEEDBACK else "NUMERIC",
        comment=comment,
        # Um score por trace/nome/usuário: votar de novo substitui o voto anterior.
        score_id=Langfuse.create_trace_id(seed=f"{trace_id}:{name}:{user_id}") if user_id else None,
        metadata={"user_id": user_id} if user_id else None,
    )
    return trace_id
