"""O panorama do dashboard (`observability/overview.py`): série sem buracos no fuso
pedido, período anterior, uma linha por agente com as versões, tools que falham
e os testes do Playground (`dry_run`) fora por padrão."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from agent_service.api.observability_routes import overview
from agent_service.observability import run_store, trace_store
from agent_service.observability.overview import _percentile, auto_granularity, build_overview
from agent_service.observability.run_store import RunRecord, SpanRecord, save_score

UTC = timezone.utc
# Uma janela só deste arquivo: o banco da suíte é compartilhado.
BASE = datetime(2031, 3, 10, tzinfo=UTC)


@pytest.fixture(autouse=True)
def local_backend():
    trace_store.set_trace_store(None)
    yield
    trace_store.set_trace_store(None)


@pytest.fixture
def agente() -> str:
    return f"painel-{uuid4().hex[:8]}"


def gravar(agent_type, started_at, *, status="success", version=1, latency_ms=1000.0, cost=0.01,
           session=None, tool_failures=0, tools=(), metadata=None) -> str:
    run_id = str(uuid4())
    spans = [
        SpanRecord(type="TOOL", name=name, started_at=started_at,
                   level="ERROR" if i < tool_failures else "DEFAULT",
                   metadata={"failure": "unavailable", "http_status": 500} if i < tool_failures else {})
        for i, name in enumerate(tools)
    ]
    run_store._write_run(RunRecord(
        run_id=run_id, trace_id=run_id.replace("-", ""), agent_type=agent_type, agent_name=agent_type.upper(),
        prompt_version=1, endpoint="chat", user_id="u", session_id=session or f"s-{uuid4().hex[:6]}",
        message="oi", started_at=started_at, ended_at=started_at + timedelta(milliseconds=latency_ms),
        status=status, cost_usd=cost, total_tokens=100, agent_version=version, spans=spans, metadata=metadata or {},
    ))
    return run_id


def painel(agente, since, until, **kwargs):
    return build_overview(since=since, until=until, agent_type=agente, **kwargs)


def test_dias_sem_execucao_viram_zero_e_o_fuso_decide_o_dia(agente):
    # 01:30 UTC do dia 11 ainda é dia 10 em São Paulo (UTC-3).
    gravar(agente, BASE + timedelta(days=1, hours=1, minutes=30))
    gravar(agente, BASE + timedelta(days=4, hours=15))
    p = painel(agente, BASE, BASE + timedelta(days=7))

    assert p.granularity == "day"
    assert len(p.buckets) == 8  # 10 a 17 no fuso local: o dia 10 começa às 03:00 UTC
    por_dia = {b.start[:10]: b.runs for b in p.buckets}
    assert por_dia["2031-03-10"] == 1, "01:30 UTC conta no dia anterior em São Paulo"
    assert por_dia["2031-03-11"] == 0
    assert por_dia["2031-03-14"] == 1
    assert sum(por_dia.values()) == 2


def test_granularidade_automatica():
    assert auto_granularity(BASE, BASE + timedelta(hours=24)) == "hour"
    assert auto_granularity(BASE, BASE + timedelta(days=30)) == "day"
    assert auto_granularity(BASE, BASE + timedelta(days=180)) == "week"


def test_totais_separam_erro_interrompido_e_tool_falhando(agente):
    t = BASE + timedelta(hours=12)
    gravar(agente, t)
    gravar(agente, t, status="error")
    gravar(agente, t, status="interrupted")
    gravar(agente, t, tools=("ficha", "lead"), tool_failures=1)
    p = painel(agente, BASE, BASE + timedelta(days=1))

    assert (p.totals.runs, p.totals.success, p.totals.errors, p.totals.interrupted) == (4, 2, 1, 1)
    assert p.totals.tool_failure_runs == 1
    assert (p.totals.tool_calls, p.totals.tool_failures) == (2, 1)
    bucket = next(b for b in p.buckets if b.runs)
    assert (bucket.success, bucket.tool_failure_runs, bucket.errors) == (1, 1, 2)


def test_testes_do_playground_ficam_de_fora_por_padrao(agente):
    t = BASE + timedelta(hours=12)
    gravar(agente, t)
    gravar(agente, t, metadata={"dry_run": "true"})
    assert painel(agente, BASE, BASE + timedelta(days=1)).totals.runs == 1
    assert painel(agente, BASE, BASE + timedelta(days=1), include_dry_run=True).totals.runs == 2


def test_periodo_anterior_para_as_variacoes(agente):
    gravar(agente, BASE + timedelta(days=-3))
    gravar(agente, BASE + timedelta(days=-2))
    gravar(agente, BASE + timedelta(days=1))
    p = painel(agente, BASE, BASE + timedelta(days=7))
    assert p.totals.runs == 1
    assert p.previous is not None and p.previous.runs == 2


def test_versoes_do_agente_com_metricas_proprias(agente):
    t = BASE + timedelta(hours=12)
    for _ in range(3):
        gravar(agente, t, version=1, cost=0.02)
    gravar(agente, t, version=1, status="error", cost=0.02)
    for _ in range(2):
        gravar(agente, t + timedelta(hours=2), version=2, cost=0.01)
    run_id = gravar(agente, t + timedelta(hours=2), version=2, cost=0.01)
    save_score(run_id=run_id, name="feedback", value=0, user_id="avaliador")

    [linha] = painel(agente, BASE, BASE + timedelta(days=1)).agents
    v2, v1 = linha.versions
    assert (v2.agent_version, v2.runs, v2.error_rate, v2.feedback_down) == (2, 3, 0.0, 1)
    assert (v1.agent_version, v1.runs, v1.error_rate) == (1, 4, 0.25)
    assert v1.cost_per_run_usd == pytest.approx(0.02)
    assert linha.totals.runs == 7
    assert sum(linha.trend) == 7


def test_custo_por_conversa(agente):
    t = BASE + timedelta(hours=12)
    gravar(agente, t, session="conversa-1", cost=0.03)
    gravar(agente, t, session="conversa-1", cost=0.01)
    gravar(agente, t, session="conversa-2", cost=0.02)
    [linha] = painel(agente, BASE, BASE + timedelta(days=1)).agents
    assert linha.totals.sessions == 2
    assert linha.cost_per_session_usd == pytest.approx(0.03)


def test_tools_que_falham_agrupadas_por_tipo(agente):
    t = BASE + timedelta(hours=12)
    gravar(agente, t, tools=("ficha",), tool_failures=1)
    gravar(agente, t + timedelta(hours=1), tools=("ficha",), tool_failures=1)
    [falha] = painel(agente, BASE, BASE + timedelta(days=1)).tool_failures
    assert (falha.tool_name, falha.failure, falha.count, falha.http_status) == ("ficha", "unavailable", 2, [500])
    assert falha.agent_types == [agente]


def test_p95_por_interpolacao():
    assert _percentile([], 0.95) is None
    assert _percentile([100.0] * 19 + [2000.0], 0.95) == pytest.approx(195.0)


def test_rota_recusa_fuso_invalido_e_intervalo_invertido():
    with pytest.raises(HTTPException) as fuso:
        overview(since=BASE, until=BASE + timedelta(days=1), tz="Marte/Olympus")
    assert fuso.value.status_code == 422
    with pytest.raises(HTTPException) as invertido:
        overview(since=BASE + timedelta(days=1), until=BASE)
    assert invertido.value.status_code == 422
