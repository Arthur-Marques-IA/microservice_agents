"""Observabilidade exposta pelo serviço: configuração, trace de um run e scores.

Os traces ficam no Langfuse (ver `observability/tracing.py`). Estas rotas são
o contrato estável para o console e para outros módulos: descobrir o trace de
um `run_id` e registrar avaliações (feedback do usuário final, notas de evals)
sem precisar falar com o Langfuse diretamente.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from agent_service.observability import tracing

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
