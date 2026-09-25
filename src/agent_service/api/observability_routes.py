"""Observabilidade exposta pelo serviço: execuções, traces e scores.

As execuções ficam no trace store local (`observability/run_store.py`), e o
Langfuse, quando ligado, é só um exportador a mais. Ninguém precisa abrir o Langfuse: estas rotas são o contrato estável para o console e
para outros módulos — listar as execuções de um agente, ler o trace completo
de um `run_id` e registrar avaliações (feedback do usuário final, notas de evals).
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from agent_service.observability import tracing
from agent_service.observability.trace_store import (
    RunPage,
    RunQuery,
    RunStats,
    RunStatus,
    RunTrace,
    SessionPage,
    TraceStore,
    TraceStoreError,
    get_trace_store,
)

router = APIRouter(prefix="/observability", tags=["observability"])


class ObservabilityConfigOut(BaseModel):
    enabled: bool
    """As execuções estão sendo registradas e podem ser lidas (`/observability/runs`...).
    Sempre `true` com o trace store local, o padrão."""
    langfuse: bool = False
    """O exportador do Langfuse está ligado."""
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
        raise HTTPException(
            status_code=503,
            detail="TRACE_STORE_BACKEND=langfuse, mas o Langfuse não está configurado neste serviço.",
        )
    return store


def _parse_meta(meta: list[str] | None) -> tuple[tuple[str, str], ...]:
    pairs = []
    for item in meta or []:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise HTTPException(status_code=422, detail=f"meta deve ser chave=valor, veio {item!r}")
        pairs.append((key, value))
    return tuple(pairs)


def _list_runs(
    *,
    agent_type: str | None,
    prompt_version: int | None,
    status: RunStatus | None,
    user_id: str | None,
    session_id: str | None,
    since: datetime | None,
    until: datetime | None,
    limit: int,
    cursor: str | None,
    agent_version: int | None = None,
    meta: list[str] | None = None,
) -> RunPage:
    query = RunQuery(
        agent_type=agent_type,
        prompt_version=prompt_version,
        agent_version=agent_version,
        status=status,
        user_id=user_id,
        session_id=session_id,
        since=since,
        until=until,
        limit=limit,
        cursor=cursor,
        metadata=_parse_meta(meta),
    )
    try:
        return _store().list_runs(query)
    except TraceStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/runs", response_model=RunPage)
def list_runs(
    agent_type: str | None = None,
    prompt_version: Annotated[int | None, Query(ge=1)] = None,
    status: RunStatus | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    agent_version: Annotated[int | None, Query(ge=1)] = None,
    meta: Annotated[list[str] | None, Query(description="Filtro por metadata, `chave=valor` (repetível).")] = None,
) -> RunPage:
    """Execuções de todos os agentes (ou de um só, com `agent_type`), mais recentes
    primeiro, com tokens, custo e feedback — a página `/observability` do console usa isto.

    Um run aparece logo depois de terminar (a gravação sai do caminho da resposta).
    """
    return _list_runs(
        agent_type=agent_type,
        prompt_version=prompt_version,
        status=status,
        user_id=user_id,
        session_id=session_id,
        since=since,
        until=until,
        limit=limit,
        cursor=cursor,
        agent_version=agent_version,
        meta=meta,
    )


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
    agent_version: Annotated[int | None, Query(ge=1)] = None,
    meta: Annotated[list[str] | None, Query(description="Filtro por metadata, `chave=valor` (repetível).")] = None,
) -> RunPage:
    """Execuções do agente, mais recentes primeiro, com tokens, custo e feedback.

    Um run aparece logo depois de terminar (a gravação sai do caminho da resposta).
    """
    return _list_runs(
        agent_type=agent_type,
        prompt_version=prompt_version,
        status=status,
        user_id=user_id,
        session_id=session_id,
        since=since,
        until=until,
        limit=limit,
        cursor=cursor,
        agent_version=agent_version,
        meta=meta,
    )


@router.get("/sessions", response_model=SessionPage)
def list_sessions(
    agent_type: str | None = None,
    status: RunStatus | None = None,
    user_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> SessionPage:
    """Sessões recentes (execuções agrupadas por `session_id`), com tokens, custo e feedback somados.

    No trace store local é um `GROUP BY` sobre o histórico inteiro; `scanned` diz
    quantas execuções entraram. Com `TRACE_STORE_BACKEND=langfuse` a API não agrupa
    por sessão, e isto varre só um lote das execuções mais recentes.
    """
    query = RunQuery(agent_type=agent_type, status=status, user_id=user_id, since=since, until=until, limit=limit)
    try:
        return _store().list_sessions(query)
    except TraceStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/stats", response_model=RunStats)
def run_stats(
    agent_type: str | None = None,
    prompt_version: Annotated[int | None, Query(ge=1)] = None,
    status: RunStatus | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> RunStats:
    """Série diária (execuções, erros, tokens, custo) mais contagem por status — os gráficos do console.

    No trace store local cobre o histórico inteiro; com `TRACE_STORE_BACKEND=langfuse`,
    só um lote das execuções mais recentes (ver `list_sessions`).
    """
    query = RunQuery(
        agent_type=agent_type,
        prompt_version=prompt_version,
        status=status,
        user_id=user_id,
        session_id=session_id,
        since=since,
        until=until,
    )
    try:
        return _store().get_stats(query)
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
    langfuse = tracing.get_langfuse() is not None
    return ObservabilityConfigOut(
        enabled=get_trace_store() is not None,
        langfuse=langfuse,
        project_url=tracing.project_url() if langfuse else None,
    )


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
    """Grava o score no trace store local (e o enfileira para o Langfuse, se ligado)."""
    trace_id = tracing.score_run(
        run_id=body.run_id,
        name=body.name,
        value=body.value,
        comment=body.comment,
        user_id=body.user_id,
    )
    return ScoreOut(run_id=body.run_id, trace_id=trace_id, name=body.name, value=body.value)


# -- modo shadow: referência, concordância e export -----------------------------------


class ReferenceIn(BaseModel):
    run_id: str = Field(..., min_length=1, max_length=200)
    reference: dict[str, Any]
    """A decisão que deveria ter saído — no shadow, a do agente legado, no mesmo
    formato do `result` do `/analyze`."""
    source: str = Field("legacy", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")


class ReferenceOut(BaseModel):
    run_id: str
    source: str


class FieldAgreement(BaseModel):
    field: str
    compared: int
    matched: int
    rate: float


class VersionAgreement(BaseModel):
    agent_version: int | None
    runs: int
    full_match: int
    rate: float


class Disagreement(BaseModel):
    run_id: str
    agent_version: int | None
    mismatches: list[dict[str, Any]]


class AgreementOut(BaseModel):
    agent_type: str
    runs: int
    """Runs com referência e saída estruturada — os que entram na conta."""
    skipped: int
    """Runs com referência mas sem saída comparável (erro, timeout)."""
    full_match: int
    rate: float
    """Fração de runs em que todos os campos compararam iguais."""
    fields: list[FieldAgreement]
    by_version: list[VersionAgreement]
    disagreements: list[Disagreement]
    """Os mais recentes em que discordou (até 20)."""


class ExportCase(BaseModel):
    id: str
    input: str
    dependencies: dict[str, Any] | None = None
    expected: dict[str, Any]
    agent_version: int | None = None


@router.post("/references", response_model=ReferenceOut, status_code=201)
def save_reference(body: ReferenceIn) -> ReferenceOut:
    """Grava a decisão de referência de um run (substitui se já houver).

    No shadow, quem chama executa o agente legado e o Kuro na mesma entrada e
    manda aqui a decisão do legado, com o `run_id` que o `/analyze` devolveu.
    Escopo `runtime`, como os scores."""
    from agent_service.observability import run_store

    try:
        run_store.save_reference(body.run_id, body.reference, source=body.source)
    except run_store.RunNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"Run {body.run_id!r} não encontrado (a gravação leva um instante após a resposta)."
        ) from exc
    return ReferenceOut(run_id=body.run_id, source=body.source)


def _referenced(agent_type: str, since: datetime | None, until: datetime | None, agent_version: int | None):
    from agent_service.observability import run_store

    return run_store.referenced_runs(
        RunQuery(agent_type=agent_type, since=since, until=until, agent_version=agent_version)
    )


@router.get("/agreement", response_model=AgreementOut)
def agreement(
    agent_type: str,
    since: datetime | None = None,
    until: datetime | None = None,
    agent_version: Annotated[int | None, Query(ge=1)] = None,
    fields: Annotated[str | None, Query(description="Só estes campos, separados por vírgula.")] = None,
    tolerance: Annotated[float, Query(ge=0)] = 0.01,
) -> AgreementOut:
    """Quanto a decisão do agente concorda com a referência (ex.: o legado no shadow),
    campo a campo e por versão da configuração — a mesma comparação do `kuro eval`.

    É o número que diz quando promover: "a v7 concorda em 97% com o legado"."""
    from agent_service.evaluation import compare, flatten

    wanted = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    per_field: dict[str, list[int]] = {}
    per_version: dict[int | None, list[int]] = {}
    disagreements: list[Disagreement] = []
    compared = skipped = full = 0
    for item in _referenced(agent_type, since, until, agent_version):
        if item["output"] is None:
            skipped += 1
            continue
        compared += 1
        mismatches = compare(item["reference"], item["output"], wanted, tolerance)
        wrong = {m["field"] for m in mismatches}
        for field in wanted or flatten(item["reference"]).keys():
            counts = per_field.setdefault(field, [0, 0])
            counts[0] += 1
            counts[1] += field not in wrong
        version = per_version.setdefault(item["agent_version"], [0, 0])
        version[0] += 1
        if not mismatches:
            full += 1
            version[1] += 1
        elif len(disagreements) < 20:
            disagreements.append(
                Disagreement(run_id=item["run_id"], agent_version=item["agent_version"], mismatches=mismatches)
            )
    return AgreementOut(
        agent_type=agent_type,
        runs=compared,
        skipped=skipped,
        full_match=full,
        rate=round(full / compared, 4) if compared else 0.0,
        fields=[
            FieldAgreement(field=f, compared=c, matched=m, rate=round(m / c, 4))
            for f, (c, m) in sorted(per_field.items())
        ],
        by_version=[
            VersionAgreement(agent_version=v, runs=c, full_match=m, rate=round(m / c, 4))
            for v, (c, m) in sorted(per_version.items(), key=lambda kv: (kv[0] is None, kv[0] or 0), reverse=True)
        ],
        disagreements=disagreements,
    )


@router.get("/export", response_model=list[ExportCase])
def export_cases(
    agent_type: str,
    since: datetime | None = None,
    until: datetime | None = None,
    agent_version: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> list[ExportCase]:
    """Runs com referência no formato de caso do `kuro eval`: a entrada real e a
    decisão de referência como `expected`. `kuro runs export` grava isto em JSONL."""
    cases = []
    for item in _referenced(agent_type, since, until, agent_version)[:limit]:
        cases.append(
            ExportCase(
                id=item["run_id"],
                input=item["message"] or "",
                dependencies=item["dependencies"],
                expected=item["reference"],
                agent_version=item["agent_version"],
            )
        )
    return cases

