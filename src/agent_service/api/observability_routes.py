"""Observabilidade exposta pelo serviço: execuções, traces e scores.

Os traces ficam no Langfuse (ver `observability/tracing.py`), mas ninguém
precisa abrir o Langfuse: estas rotas são o contrato estável para o console e
para outros módulos — listar as execuções de um agente, ler o trace completo
de um `run_id` e registrar avaliações (feedback do usuário final, notas de evals).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from agent_service.observability import tracing
from agent_service.observability.trace_store import (
    RunPage,
    RunQuery,
    RunStatus,
    RunTrace,
    TraceStore,
    TraceStoreError,
    get_trace_store,
)

router = APIRouter(prefix="/observability", tags=["observability"])


class ObservabilityConfigOut(BaseModel):
    enabled: bool
    project_url: str | None = None
    """Projeto na UI do Langfuse — `None` se desligado ou ainda inacessível."""


class RunTraceOut(BaseModel):
    run_id: str
    trace_id: str
    trace_url: str | None = None


class ScoreIn(BaseModel):
    run_id: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="run_id do Agno — vem em `ChatResponse.run_id` ou no `event: run` do stream",
    )
    name: str = Field(tracing.FEEDBACK, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    value: float = Field(..., description="`feedback`: 1 = positivo, 0 = negativo; demais nomes: numérico")
    comment: str | None = Field(default=None, max_length=2000)
    user_id: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def feedback_is_boolean(self) -> "ScoreIn":
        if self.name == tracing.FEEDBACK and self.value not in (0, 1):
            raise ValueError("`feedback` aceita apenas 1 (positivo) ou 0 (negativo)")
        return self


class ScoreOut(BaseModel):
    run_id: str
    trace_id: str
    name: str
    value: float


def _store() -> TraceStore:
    store = get_trace_store()
    if store is None:
        raise HTTPException(status_code=503, detail="Langfuse não está configurado neste serviço.")
    return store


@router.get("/agents/{agent_type}/runs", response_model=RunPage)
def list_agent_runs(
    agent_type: str,
    prompt_version: Annotated[int | None, Query(ge=1)] = None,
    status: RunStatus | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> RunPage:
    """Execuções do agente, mais recentes primeiro, com tokens, custo e feedback.

    Runs recém-terminados levam alguns segundos para aparecer (ingestão assíncrona).
    """
    query = RunQuery(
        agent_type=agent_type,
        prompt_version=prompt_version,
        status=status,
        user_id=user_id,
        session_id=session_id,
        since=since,
        until=until,
        limit=limit,
        cursor=cursor,
    )
    try:
        return _store().list_runs(query)
    except TraceStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/runs/{run_id}/trace", response_model=RunTrace)
def get_run_trace(run_id: str) -> RunTrace:
    """Trace completo do run: resumo, todos os spans (árvore via `parent_id`) e scores.

    404 também enquanto o run ainda está sendo indexado — tente de novo em alguns segundos.
    """
    try:
        trace = _store().get_run(run_id)
    except TraceStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if trace is None:
        raise HTTPException(
            status_code=404,
            detail="Trace não encontrado. Se o run acabou de terminar, ele ainda pode estar sendo indexado.",
        )
    return trace


@router.get("/config", response_model=ObservabilityConfigOut)
def observability_config() -> ObservabilityConfigOut:
    enabled = tracing.get_langfuse() is not None
    return ObservabilityConfigOut(enabled=enabled, project_url=tracing.project_url() if enabled else None)


@router.get("/runs/{run_id}", response_model=RunTraceOut)
def run_trace(run_id: str) -> RunTraceOut:
    trace_id = tracing.trace_id_for_run(run_id)
    project_url = tracing.project_url()
    return RunTraceOut(
        run_id=run_id,
        trace_id=trace_id,
        trace_url=f"{project_url}/traces/{trace_id}" if project_url else None,
    )


@router.post("/scores", response_model=ScoreOut, status_code=202)
def create_score(body: ScoreIn) -> ScoreOut:
    """Enfileira o score para o Langfuse — a ingestão é assíncrona, daí o 202."""
    try:
        trace_id = tracing.score_run(
            run_id=body.run_id,
            name=body.name,
            value=body.value,
            comment=body.comment,
            user_id=body.user_id,
        )
    except tracing.ObservabilityDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ScoreOut(run_id=body.run_id, trace_id=trace_id, name=body.name, value=body.value)
