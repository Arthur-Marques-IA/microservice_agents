"""Leitura dos traces: o console e outros módulos veem os runs sem abrir o Langfuse.

`TraceStore` é o contrato; `LangfuseTraceStore` o implementa sobre a API
pública do Langfuse v4 (as chaves ficam só no servidor). As respostas usam os
modelos daqui, nunca o JSON do Langfuse — trocar o backend de traces (Cloud,
Postgres próprio...) não muda o contrato de quem consome.

Como os dados estão no Langfuse (ver `tracing.py`):

- cada run tem uma observação raiz (`isRootObservation=true`, com
  `traceName=agent_type`, `version=prompt-v{N}`, `level` = status e o `run_id`
  no metadata). Atenção: a raiz pode ter `parentObservationId` não nulo;
- tokens e custo ficam nos filhos (GENERATION) — por isso somam-se todas as
  observações do trace, não a raiz;
- a ingestão é assíncrona: um run recém-terminado leva alguns segundos para
  aparecer.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel

from agent_service.config import get_settings
from agent_service.observability.tracing import FEEDBACK, get_langfuse, trace_id_for_run

RunStatus = Literal["success", "error", "interrupted"]

_LEVEL_BY_STATUS: dict[RunStatus, str] = {"success": "DEFAULT", "error": "ERROR", "interrupted": "WARNING"}
_STATUS_BY_LEVEL: dict[str, RunStatus] = {"ERROR": "error", "WARNING": "interrupted"}
# Metadata que o OpenTelemetry/Langfuse anexam a todo span — ruído para quem lê o trace.
_NOISY_METADATA_PREFIXES = ("resourceAttributes.", "scope.", "attributes.langfuse.", "attributes.session.", "attributes.user.")
_OBSERVATIONS_PAGE = 1000
_SCORES_PAGE = 100
_MAX_SCORE_PAGES = 5
_VERSION_PREFIX = "prompt-v"


class TraceStoreError(RuntimeError):
    """O backend de traces falhou ou está inacessível."""


class RunSummary(BaseModel):
    run_id: str
    trace_id: str
    agent_type: str
    agent_name: str | None = None
    prompt_version: int | None = None
    endpoint: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    environment: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    latency_ms: float | None = None
    status: RunStatus
    status_message: str | None = None
    message: str | None = None
    output: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float | None = None
    feedback_up: int | None = 0
    feedback_down: int | None = 0
    """`None` quando havia avaliações demais para contar com segurança na listagem — veja o trace."""


class RunPage(BaseModel):
    items: list[RunSummary]
    next_cursor: str | None = None


class SpanOut(BaseModel):
    id: str
    parent_id: str | None = None
    type: str
    name: str
    started_at: datetime
    ended_at: datetime | None = None
    latency_ms: float | None = None
    level: str
    status_message: str | None = None
    input: Any = None
    output: Any = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float | None = None
    metadata: dict[str, Any] = {}


class ScoreOut(BaseModel):
    id: str
    name: str
    value: float | bool | str | None
    data_type: str
    source: str
    comment: str | None = None
    user_id: str | None = None
    timestamp: datetime


class RunTrace(BaseModel):
    run: RunSummary
    spans: list[SpanOut]
    """Todas as observações do trace, em ordem de início; a árvore sai de `parent_id`."""
    scores: list[ScoreOut]


@dataclass(frozen=True)
class RunQuery:
    agent_type: str
    prompt_version: int | None = None
    status: RunStatus | None = None
    user_id: str | None = None
    session_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 50
    cursor: str | None = None
    tenant_id: str | None = None
    """Reservado para isolar clientes da API: filtra `metadata.tenant_id`."""


class TraceStore(Protocol):
    def list_runs(self, query: RunQuery) -> RunPage: ...

    def get_run(self, run_id: str, *, tenant_id: str | None = None) -> RunTrace | None: ...


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_io(value: Any) -> Any:
    """A API devolve input/output como string; JSON vira objeto para o console formatar."""
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped[:1] in ("{", "["):
        try:
            return json.loads(stripped)
        except ValueError:
            return value
    return value


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ms(seconds: Any) -> float | None:
    return round(seconds * 1000, 1) if isinstance(seconds, (int, float)) else None


class _Usage:
    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.cost_usd: float | None = None
        self.model: str | None = None

    def add(self, observation: dict[str, Any]) -> None:
        self.input_tokens += observation.get("inputUsage") or 0
        self.output_tokens += observation.get("outputUsage") or 0
        self.total_tokens += observation.get("totalUsage") or 0
        cost = observation.get("totalCost")
        if cost is not None:
            self.cost_usd = (self.cost_usd or 0) + cost
        if observation.get("model"):
            self.model = observation["model"]


class LangfuseTraceStore:
    def __init__(
        self,
        *,
        base_url: str,
        public_key: str,
        secret_key: str,
        environment: str | None,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._environment = environment
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            auth=(public_key, secret_key),
            timeout=timeout,
            transport=transport,
        )

    # -- API do Langfuse ---------------------------------------------------

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._http.get(path, params={k: v for k, v in params.items() if v is not None})
        except httpx.HTTPError as exc:
            raise TraceStoreError(f"Langfuse inacessível: {exc}") from exc
        if response.status_code >= 400:
            raise TraceStoreError(f"Langfuse respondeu {response.status_code}: {response.text[:300]}")
        return response.json()

    def _observations(self, filters: list[dict[str, Any]], *, fields: str, limit: int, cursor: str | None = None) -> dict[str, Any]:
        # `filter` tem precedência sobre os filtros por query param — tudo vai nele.
        return self._get(
            "/api/public/v2/observations",
            {"filter": json.dumps(filters), "fields": fields, "limit": limit, "cursor": cursor},
        )

    def _all_observations(self, filters: list[dict[str, Any]], *, fields: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page = self._observations(filters, fields=fields, limit=_OBSERVATIONS_PAGE, cursor=cursor)
            items.extend(page.get("data", []))
            cursor = page.get("meta", {}).get("cursor")
            if not cursor or not page.get("data"):
                return items

    def _scores(self, **params: Any) -> tuple[list[dict[str, Any]], bool]:
        """Scores que casam com os filtros e se a lista está completa (não bateu no limite de páginas)."""
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(_MAX_SCORE_PAGES):
            page = self._get(
                "/api/public/v3/scores",
                {**params, "fields": "details,subject", "limit": _SCORES_PAGE, "cursor": cursor},
            )
            items.extend(page.get("data", []))
            cursor = page.get("meta", {}).get("cursor")
            if not cursor:
                return items, True
        return items, False

    def _scope_filters(self, tenant_id: str | None) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = []
        if self._environment:
            filters.append({"type": "stringOptions", "column": "environment", "operator": "any of", "value": [self._environment]})
        if tenant_id:
            filters.append({"type": "stringObject", "column": "metadata", "key": "tenant_id", "operator": "=", "value": tenant_id})
        return filters

    # -- TraceStore --------------------------------------------------------

    def list_runs(self, query: RunQuery) -> RunPage:
        filters = self._scope_filters(query.tenant_id) + [
            {"type": "boolean", "column": "isRootObservation", "operator": "=", "value": True},
            {"type": "string", "column": "traceName", "operator": "=", "value": query.agent_type},
        ]
        if query.prompt_version is not None:
            filters.append({"type": "string", "column": "version", "operator": "=", "value": f"{_VERSION_PREFIX}{query.prompt_version}"})
        if query.status:
            filters.append({"type": "string", "column": "level", "operator": "=", "value": _LEVEL_BY_STATUS[query.status]})
        if query.user_id:
            filters.append({"type": "string", "column": "userId", "operator": "=", "value": query.user_id})
        if query.session_id:
            filters.append({"type": "string", "column": "sessionId", "operator": "=", "value": query.session_id})
        if query.since:
            filters.append({"type": "datetime", "column": "startTime", "operator": ">=", "value": _iso(query.since)})
        if query.until:
            filters.append({"type": "datetime", "column": "startTime", "operator": "<", "value": _iso(query.until)})

        page = self._observations(filters, fields="basic,io,metadata,metrics", limit=query.limit, cursor=query.cursor)
        roots = [r for r in page.get("data", []) if (r.get("metadata") or {}).get("run_id")]
        next_cursor = page.get("meta", {}).get("cursor") if page.get("data") else None
        if not roots:
            return RunPage(items=[], next_cursor=next_cursor)

        trace_ids = [r["traceId"] for r in roots]
        usage = {trace_id: _Usage() for trace_id in trace_ids}
        for observation in self._all_observations(
            [{"type": "stringOptions", "column": "traceId", "operator": "any of", "value": trace_ids}],
            fields="usage,model",
        ):
            if observation["traceId"] in usage:
                usage[observation["traceId"]].add(observation)

        # A API de scores não filtra vários traces de uma vez: busca o feedback do
        # projeto desde o run mais antigo da página e cruza aqui. Se passar do limite
        # de páginas, as contagens ficam desconhecidas (None) — nunca uma soma parcial.
        votes = {trace_id: [0, 0] for trace_id in trace_ids}
        oldest = min(r["startTime"] for r in roots)
        scores, complete = self._scores(name=FEEDBACK, fromTimestamp=oldest, dataType="BOOLEAN")
        for score in scores:
            subject = score.get("subject") or {}
            trace_id = subject.get("traceId") or subject.get("id")
            if trace_id in votes:
                votes[trace_id][0 if score.get("value") else 1] += 1

        items = []
        for root in roots:
            summary = self._summary(root, usage[root["traceId"]])
            if complete:
                summary.feedback_up, summary.feedback_down = votes[root["traceId"]]
            else:
                summary.feedback_up = summary.feedback_down = None
            items.append(summary)
        return RunPage(items=items, next_cursor=next_cursor)

    def get_run(self, run_id: str, *, tenant_id: str | None = None) -> RunTrace | None:
        trace_id = trace_id_for_run(run_id)
        observations = self._all_observations(
            self._scope_filters(tenant_id)
            + [{"type": "string", "column": "traceId", "operator": "=", "value": trace_id}],
            fields="core,basic,io,metadata,model,usage,metrics",
        )
        root = next((o for o in observations if o.get("isRootObservation")), None)
        if root is None:
            return None

        usage = _Usage()
        for observation in observations:
            usage.add(observation)
        spans = sorted((self._span(o, root) for o in observations), key=lambda s: s.started_at)
        trace_scores, complete = self._scores(traceId=trace_id)
        scores = [self._score(s) for s in trace_scores]
        run = self._summary(root, usage)
        feedback = [s for s in scores if s.name == FEEDBACK and s.data_type == "BOOLEAN"]
        if complete:
            run.feedback_up = sum(1 for s in feedback if s.value)
            run.feedback_down = len(feedback) - run.feedback_up
        else:
            run.feedback_up = run.feedback_down = None
        return RunTrace(run=run, spans=spans, scores=scores)

    # -- conversão ---------------------------------------------------------

    @staticmethod
    def _summary(root: dict[str, Any], usage: _Usage) -> RunSummary:
        metadata = root.get("metadata") or {}
        run_input = _parse_io(root.get("input"))
        message = run_input.get("message") if isinstance(run_input, dict) else run_input
        version = _to_int(metadata.get("prompt_version"))
        if version is None and str(root.get("version") or "").startswith(_VERSION_PREFIX):
            version = _to_int(root["version"][len(_VERSION_PREFIX) :])
        return RunSummary(
            run_id=str(metadata["run_id"]),
            trace_id=root["traceId"],
            agent_type=str(metadata.get("agent_type") or root.get("traceName") or ""),
            agent_name=metadata.get("agent_name"),
            prompt_version=version,
            endpoint=metadata.get("endpoint") or root.get("name"),
            user_id=root.get("userId") or None,
            session_id=root.get("sessionId") or None,
            environment=root.get("environment") or None,
            started_at=root["startTime"],
            ended_at=root.get("endTime"),
            latency_ms=_ms(root.get("latency")),
            status=_STATUS_BY_LEVEL.get(root.get("level") or "", "success"),
            status_message=root.get("statusMessage") or None,
            message=message if isinstance(message, str) else None,
            output=root.get("output") if isinstance(root.get("output"), str) else None,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cost_usd=usage.cost_usd,
        )

    @staticmethod
    def _span(observation: dict[str, Any], root: dict[str, Any]) -> SpanOut:
        is_root = observation["id"] == root["id"]
        metadata = {
            key.removeprefix("attributes."): value
            for key, value in (observation.get("metadata") or {}).items()
            if not key.startswith(_NOISY_METADATA_PREFIXES)
        }
        return SpanOut(
            id=observation["id"],
            # A raiz pode apontar para um pai externo (o contexto remoto do trace): no console ela é a raiz.
            parent_id=None if is_root else observation.get("parentObservationId"),
            type=observation.get("type") or "SPAN",
            name=observation.get("name") or "",
            started_at=observation["startTime"],
            ended_at=observation.get("endTime"),
            latency_ms=_ms(observation.get("latency")),
            level=observation.get("level") or "DEFAULT",
            status_message=observation.get("statusMessage") or None,
            input=_parse_io(observation.get("input")),
            output=_parse_io(observation.get("output")),
            model=observation.get("model") or None,
            input_tokens=observation.get("inputUsage") or 0,
            output_tokens=observation.get("outputUsage") or 0,
            total_tokens=observation.get("totalUsage") or 0,
            cost_usd=observation.get("totalCost"),
            metadata=metadata,
        )

    @staticmethod
    def _score(score: dict[str, Any]) -> ScoreOut:
        metadata = score.get("metadata") or {}
        return ScoreOut(
            id=score["id"],
            name=score["name"],
            value=score.get("value"),
            data_type=score.get("dataType") or "NUMERIC",
            source=score.get("source") or "API",
            comment=score.get("comment") or None,
            user_id=metadata.get("user_id") if isinstance(metadata, dict) else None,
            timestamp=score["timestamp"],
        )


_store: TraceStore | None = None


def get_trace_store() -> TraceStore | None:
    """`None` quando o Langfuse está desligado — as rotas respondem 503."""
    global _store
    if _store is None and get_langfuse() is not None:
        settings = get_settings()
        _store = LangfuseTraceStore(
            base_url=settings.langfuse_base_url,
            public_key=settings.langfuse_public_key or "",
            secret_key=settings.langfuse_secret_key or "",
            environment=settings.langfuse_environment,
            timeout=settings.langfuse_timeout_seconds,
        )
    return _store


def set_trace_store(store: TraceStore | None) -> None:
    """Para testes."""
    global _store
    _store = store
