"""TUI `kuro dash` dirigida pelo Pilot do Textual, contra um cliente falso."""

import pytest

pytest.importorskip("textual")

from textual.widgets import DataTable, Static, Tree  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from agent_service.cli import main as cli_main  # noqa: E402
from agent_service.cli.client import ApiError, ServiceUnavailable  # noqa: E402
from agent_service.tui.app import KuroDash, RunScreen  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


RUN = {
    "run_id": "r1",
    "agent_type": "suporte",
    "agent_version": 3,
    "status": "success",
    "started_at": "2026-10-03T12:30:00Z",
    "latency_ms": 1500,
    "total_tokens": 120,
    "cost_usd": 0.0012,
    "message": "meu wifi caiu",
    "output": "Vamos ver.",
    "session_id": "s1",
}

TRACE = {
    "run": RUN,
    "spans": [
        {"id": "a", "parent_id": None, "type": "GENERATION", "name": "gemini", "started_at": "1", "level": "DEFAULT",
         "latency_ms": 900, "input": "x", "output": "y"},
        {"id": "b", "parent_id": "a", "type": "TOOL", "name": "ficha", "started_at": "2", "level": "ERROR",
         "status_message": "HTTP 500", "input": {"cpf": "1"}, "output": None},
    ],
    "scores": [{"name": "eval", "value": 1, "comment": "ok"}],
}

OVERVIEW = {
    "totals": {"runs": 10, "errors": 1, "tool_failure_runs": 2, "sessions": 4, "total_tokens": 5000,
               "cost_usd": 0.5, "feedback_up": 3, "feedback_down": 1},
    "previous": {"runs": 5, "total_tokens": 2500, "cost_usd": 0.25},
    "agents": [{"agent_type": "suporte", "last_run_at": "2026-10-03T12:30:00Z",
                "totals": {"runs": 10, "errors": 1, "tool_failure_runs": 2, "total_tokens": 5000, "cost_usd": 0.5,
                           "feedback_up": 3, "feedback_down": 1}}],
    "tool_failures": [{"tool_name": "ficha", "failure": "http_5xx", "count": 2, "agent_types": ["suporte"],
                       "http_status": [500], "last_at": "2026-10-03T12:30:00Z"}],
}


class FakeClient:
    base_url = "http://kuro.test"

    def __init__(self, *, runs=None, overview=None):
        self.runs = runs
        self.overview_result = overview
        self.run_queries: list[dict] = []

    def health(self):
        return {"version": "0.2.0"}

    def list_runs(self, **params):
        self.run_queries.append(params)
        if isinstance(self.runs, Exception):
            raise self.runs
        return {"items": self.runs if self.runs is not None else [RUN]}

    def run_trace(self, run_id):
        return TRACE

    def overview(self, **params):
        if isinstance(self.overview_result, Exception):
            raise self.overview_result
        return self.overview_result or OVERVIEW


def _text(widget: Static) -> str:
    return str(widget.render())


async def test_runs_table_and_trace_screen():
    app = KuroDash(FakeClient(), interval=60)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        table = app.query_one("#runs", DataTable)
        assert table.row_count == 1
        assert "meu wifi caiu" in str(table.get_row_at(0))
        table.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, RunScreen)
        await app.workers.wait_for_complete()
        await pilot.pause()
        tree = app.screen.query_one(Tree)
        labels = [str(node.label) for node in tree.root.children]
        assert any("gemini" in label for label in labels)
        tool = next(n for n in tree.root.children[0].children if "ficha" in str(n.label))
        assert tool.is_expanded and tool.parent.is_expanded  # o span com erro fica à vista
        assert any("HTTP 500" in str(n.label) for n in tool.children)
        assert "eval = 1" in _text(app.screen.query_one("#scores", Static))
        await pilot.press("escape")
        assert not isinstance(app.screen, RunScreen)


async def test_agent_filter_is_sent():
    client = FakeClient()
    app = KuroDash(client, interval=60, agent="r8")
    async with app.run_test(size=(140, 40)) as pilot:
        await app.workers.wait_for_complete()
        assert client.run_queries[0]["agent_type"] == "r8"
        app.query_one("#agent").value = "suporte"
        app.query_one("#agent").focus()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert client.run_queries[-1]["agent_type"] == "suporte"


async def test_service_down_shows_message_instead_of_crashing():
    app = KuroDash(FakeClient(runs=ServiceUnavailable("não consegui falar com http://kuro.test")), interval=60)
    async with app.run_test(size=(140, 40)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "não consegui falar" in _text(app.query_one("#runs-status", Static))


async def test_overview_renders_totals_agents_and_failures():
    app = KuroDash(FakeClient(), interval=60)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("2")
        await app.workers.wait_for_complete()
        await pilot.pause()
        totals = _text(app.query_one("#totals", Static))
        assert "10" in totals and "+100%" in totals
        assert app.query_one("#agents", DataTable).row_count == 1
        assert app.query_one("#tool-failures", DataTable).row_count == 1


async def test_overview_without_admin_scope_explains():
    app = KuroDash(FakeClient(overview=ApiError(403, "escopo insuficiente")), interval=60)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("2")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "escopo admin" in _text(app.query_one("#totals", Static))


def test_dash_without_tty_fails_with_usage_error():
    result = CliRunner().invoke(cli_main.app, ["dash"])
    assert result.exit_code == 2
    assert "TTY" in result.output
