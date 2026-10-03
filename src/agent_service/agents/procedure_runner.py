"""Um turno de conversa com um agente procedural.

A ordem é o que garante as regras de `agents/procedural.py`:

1. carrega (ou cria) o estado da sessão em `procedure_runs`;
2. **extrai** da mensagem os valores dos campos — uma chamada estruturada ao
   modelo, revalidada aqui;
3. **aplica** as regras de transição (código, não modelo) e grava o estado;
4. se a etapa atual é uma `action`, **reserva** a ação (grava `running` com a
   trava otimista), chama a tool e grava o resultado — tudo *antes* de responder,
   para uma resposta que estoure o tempo não apagar um efeito que já aconteceu;
5. **responde**: na etapa `confirm`, com o texto montado dos dados; nas outras, o
   modelo redige a partir de `dependencies.procedimento`.

Tudo isso é uma execução só no trace: a extração e a ação entram como spans do
mesmo run, e a etapa em que a conversa ficou vai em `metadata.procedure_stage`.
"""

import asyncio
import dataclasses
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from datetime import datetime, timedelta, timezone
from typing import Any

from agno.agent import Agent
from agno.run.agent import RunEvent
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from agent_service.agents import procedural, procedure_store
from agent_service.agents.base import build_agent
from agent_service.agents.procedure_store import ProcedureConflictError
from agent_service.observability.run_store import SpanRecord
from agent_service.observability.tracing import (
    RUN_FAILED,
    RunContext,
    RunTimeoutError,
    _model_spans,
    record_run_without_model,
    traced_run_events,
)
from agent_service.tools.invoke import ToolUnavailableError, invoke_tool

logger = logging.getLogger(__name__)

STALE_ACTION = timedelta(minutes=10)
"""Uma ação `running` há mais que isso foi interrompida (o processo caiu no meio)."""

_extractors: dict[str, tuple[Any, Agent]] = {}


class ProcedureBusyError(RuntimeError):
    """Outra mensagem da mesma sessão está sendo processada — 409 para quem chama."""


def _busy(session_id: str) -> ProcedureBusyError:
    return ProcedureBusyError(
        f"Outra mensagem da sessão {session_id!r} está sendo processada. Espere a resposta dela e envie de novo."
    )


def is_procedural(run: RunContext) -> bool:
    return bool(run.definition) and (run.definition.get("kind") or "conversational") == "procedural"


# -- extração --------------------------------------------------------------------------


def _extractor_agent(definition: dict[str, Any]) -> Agent:
    """Um agente one-shot com o schema da extração, no mesmo modelo do agente.
    Em cache pela definição: muda quando as etapas ou o modelo mudam."""
    key = definition["agent_type"]
    stamp = definition.get("updated_at")
    cached = _extractors.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    agent = build_agent(
        agent_id=f"{key}-extracao",
        name=f"{definition['name']} (extração)",
        instructions=procedural.EXTRACTION_INSTRUCTIONS,
        model_provider=definition.get("model_provider"),
        model_id=definition.get("model_id"),
        model_credential_id=definition.get("model_credential_id"),
        model_params=definition.get("model_params"),
        kind="analysis",
        output_schema=procedural.extraction_model(key, definition.get("stages") or []),
    )
    _extractors[key] = (stamp, agent)
    return agent


async def extract(
    definition: dict[str, Any], state: dict[str, Any], message: str, last_reply: str | None
) -> tuple[dict[str, Any], list[SpanRecord]]:
    """Os valores que a mensagem traz, e os spans da chamada ao modelo."""
    stages = definition.get("stages") or []
    prompt = procedural.extraction_prompt(stages, state, message, last_reply)
    started = datetime.now(timezone.utc)
    agent = await run_in_threadpool(_extractor_agent, definition)
    output = await agent.arun(prompt, stream=False)
    content = getattr(output, "content", None)
    extracted = content.model_dump() if isinstance(content, BaseModel) else {}
    spans = _model_spans(getattr(output, "metrics", None), started) or [
        SpanRecord(type="GENERATION", name="extracao", started_at=started)
    ]
    for span in spans:
        span.name = f"extracao · {span.name}"
        span.input = prompt
        span.output = extracted
        span.ended_at = datetime.now(timezone.utc)
    return extracted, spans


# -- ação ---------------------------------------------------------------------------------


async def _execute_action(
    stage: dict[str, Any], state: dict[str, Any], row: dict[str, Any], run: RunContext, timeout: float | None
) -> tuple[dict[str, Any], SpanRecord]:
    attempt = state["actions"][stage["id"]]["attempts"]
    slots = dict(state["slots"])
    dependencies = {
        **(run.dependencies or {}),
        **slots,
        # Estável por tentativa: quem implementa a tool consegue descartar uma
        # entrega repetida da mesma tentativa.
        "idempotency_key": f"{row['id']}:{stage['id']}:{attempt}",
    }
    started = datetime.now(timezone.utc)
    try:
        call = invoke_tool(
            stage["tool"],
            slots,
            function_name=stage.get("function"),
            dependencies=dependencies,
            dry_run=run.dry_run,
            lenient_arguments=True,
        )
        outcome = await (asyncio.wait_for(call, timeout) if timeout else call)
    except ToolUnavailableError as exc:
        outcome = {"ok": False, "error": str(exc), "failure": "config"}
    except TimeoutError:
        outcome = {
            "ok": False,
            "error": "a ação passou do tempo limite — confira no sistema de destino se ela aconteceu antes de tentar de novo",
            "failure": "unavailable",
        }
    span = SpanRecord(
        type="TOOL",
        name=stage["tool"],
        started_at=started,
        ended_at=datetime.now(timezone.utc),
        level="DEFAULT" if outcome.get("ok") else "ERROR",
        status_message=None if outcome.get("ok") else str(outcome.get("error"))[:500],
        input=slots,
        output=outcome.get("result"),
        metadata={
            "procedure_stage": stage["id"],
            "attempt": attempt,
            **({"failure": outcome["failure"]} if outcome.get("failure") and not outcome.get("ok") else {}),
            **({"http_status": outcome["http_status"]} if outcome.get("http_status") else {}),
        },
    )
    return outcome, span


# -- turno ------------------------------------------------------------------------------------


def _stage_id(stages: list[dict[str, Any]], state: dict[str, Any]) -> str | None:
    index = procedural.current_index(stages, state)
    return stages[index]["id"] if index is not None else None


async def _save(row: dict[str, Any], state: dict[str, Any], stages: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            procedure_store.save_procedure, row, state=state, stage=_stage_id(stages, state), **extra
        )
    except ProcedureConflictError as exc:
        raise _busy(row["session_id"]) from exc


async def run_procedural_turn(agent: Agent, run: RunContext) -> AsyncIterator[tuple[str, Any]]:
    """Eventos `("message", texto)`, `("usage", métricas)`, `("error", motivo)` e,
    por último, `("state", estado)`. Levanta `ProcedureBusyError` (409) e
    `RunTimeoutError` (504)."""
    definition = run.definition or {}
    stages = definition.get("stages") or []
    timeout = run.timeout_seconds
    dependencies = dict(run.dependencies or {})

    row = await run_in_threadpool(procedure_store.get_procedure, run.agent_type, run.session_id)
    if row is None:
        initial = procedural.new_state(stages, dependencies)
        try:
            row = await run_in_threadpool(
                lambda: procedure_store.create_procedure(
                    agent_type=run.agent_type,
                    session_id=run.session_id,
                    user_id=run.user_id,
                    state=initial,
                    stage=_stage_id(stages, initial),
                    dry_run=run.dry_run,
                )
            )
        except ProcedureConflictError as exc:
            raise _busy(run.session_id) from exc
    state = row["state"]
    last_reply = row.get("last_reply")
    spans: list[SpanRecord] = []

    # 1-3. extração e transição
    if procedural.current_index(stages, state) is not None:
        try:
            call = extract(definition, state, run.message, last_reply)
            extracted, extraction_spans = await (asyncio.wait_for(call, timeout) if timeout else call)
        except TimeoutError:
            raise RunTimeoutError(f"Tempo limite de {timeout:g}s excedido na extração.") from None
        spans.extend(extraction_spans)
        state, _ = procedural.apply_extraction(stages, state, extracted)
        row = await _save(row, state, stages)

    # 4. ações: reservar, executar e gravar antes de responder
    action_error: str | None = None
    while (index := procedural.current_index(stages, state)) is not None and stages[index]["type"] == "action":
        stage = stages[index]
        current = state["actions"].get(stage["id"]) or {}
        if current.get("status") == "running":
            updated_at = row.get("updated_at")
            if isinstance(updated_at, datetime) and updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            if updated_at is None or datetime.now(timezone.utc) - updated_at < STALE_ACTION:
                raise _busy(run.session_id)
            # O processo caiu no meio da ação: não dá para saber se ela aconteceu.
            state = procedural.finish_action(
                stages,
                state,
                stage["id"],
                {"ok": False, "error": "a ação foi interrompida — confira no sistema de destino antes de confirmar de novo"},
            )
            row = await _save(row, state, stages)
            action_error = state["actions"][stage["id"]]["error"]
            break
        state = procedural.start_action(state, stage["id"])
        row = await _save(row, state, stages)  # a reserva: outra mensagem não executa a mesma ação
        outcome, span = await _execute_action(stage, state, row, run, timeout)
        spans.append(span)
        state = procedural.finish_action(stages, state, stage["id"], outcome)
        row = await _save(row, state, stages)
        if not outcome.get("ok"):
            action_error = state["actions"][stage["id"]]["error"]
            break

    view = procedural.state_view(stages, state)
    turn = dataclasses.replace(
        run,
        extra_spans=tuple(spans),
        metadata={**run.metadata, "procedure_stage": view["stage"] or "done"},
    )

    # 5. resposta
    index = procedural.current_index(stages, state)
    reply: str
    if index is not None and stages[index]["type"] == "confirm" and not state.get("declined") and not action_error:
        reply = procedural.confirmation_text(stages, state, index)
        await run_in_threadpool(record_run_without_model, turn, reply)
        yield "message", reply
    else:
        context = procedural.reply_context(stages, state, last_reply=last_reply, action_error=action_error)
        turn = dataclasses.replace(turn, dependencies={**dependencies, "procedimento": context})
        chunks: list[str] = []
        final: str | None = None
        async with aclosing(traced_run_events(agent, turn)) as events:
            async for event in events:
                if event.event == RunEvent.run_content.value and event.content:
                    chunks.append(event.content)
                    yield "message", event.content
                elif event.event == RunEvent.run_completed.value:
                    if isinstance(event.content, str):
                        final = event.content
                    if event.metrics:
                        yield "usage", event.metrics.to_dict()
                elif event.event == RunEvent.run_error.value:
                    yield "error", event.content or RUN_FAILED
        reply = final if final is not None else "".join(chunks)
        if final is not None and not chunks:
            yield "message", final

    try:
        await run_in_threadpool(procedure_store.save_procedure, row, state=state, stage=view["stage"], last_reply=reply)
    except ProcedureConflictError:
        logger.info("Última resposta da sessão %r não gravada: outra mensagem gravou antes", run.session_id)
    yield "state", view
