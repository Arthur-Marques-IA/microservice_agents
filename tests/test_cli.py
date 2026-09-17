"""CLI `kuro` contra uma API falsa (httpx.MockTransport) — sem serviço no ar."""

import json

import httpx
import pytest
from typer.testing import CliRunner

from agent_service.cli import main as cli_main
from agent_service.cli.client import Client

AGENT = {
    "agent_type": "suporte",
    "name": "Suporte",
    "instructions": ["Seja breve."],
    "tools": [],
    "model_provider": None,
    "model_id": None,
    "dependency_fields": [
        {"name": "cpf", "type": "string", "label": "CPF", "description": "", "required": True, "default": None}
    ],
    "memory_backend": "common",
    "num_history_runs": 10,
    "is_seed": False,
    "prompt_version": 1,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}

runner = CliRunner()


@pytest.fixture
def api(monkeypatch, tmp_path):
    """Registra as requisições feitas e responde por (método, caminho)."""
    monkeypatch.setenv("KURO_HOME", str(tmp_path))
    calls: list[httpx.Request] = []
    routes: dict[tuple[str, str], httpx.Response] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        response = routes.get((request.method, request.url.path))
        return response if response is not None else httpx.Response(404, json={"detail": "não encontrado"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(cli_main, "Client", lambda url, timeout: Client(url, timeout, transport=transport))
    return routes, calls


def _run(*args: str, input: str | None = None):
    return runner.invoke(cli_main.app, list(args), input=input)


def test_agents_list_json(api):
    routes, _ = api
    routes[("GET", "/agents")] = httpx.Response(200, json=[AGENT])
    result = _run("--json", "agents", "list")
    assert result.exit_code == 0
    assert json.loads(result.stdout)[0]["agent_type"] == "suporte"


def test_agents_without_tty_lists_instead_of_prompting(api):
    routes, _ = api
    routes[("GET", "/agents")] = httpx.Response(200, json=[AGENT])
    assert _run("agents").exit_code == 0


def test_api_error_exit_code_and_json_error(api):
    result = _run("--json", "agents", "get", "nao-existe")
    assert result.exit_code == 1
    assert json.loads(result.stderr)["status"] == 404


def test_service_unavailable_exit_code(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("recusado", request=request)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(cli_main, "Client", lambda url, timeout: Client(url, timeout, transport=transport))
    assert _run("agents", "list").exit_code == 3


def test_set_sends_only_given_fields(api):
    routes, calls = api
    routes[("PUT", "/agents/suporte")] = httpx.Response(200, json=AGENT)
    result = _run("agents", "set", "suporte", "num_history_runs=3", "instructions=Nova instrução")
    assert result.exit_code == 0
    assert json.loads(calls[-1].content) == {"num_history_runs": 3, "instructions": ["Nova instrução"]}


def test_set_rejects_non_editable_field(api):
    assert _run("agents", "set", "suporte", "is_seed=true").exit_code == 2


def test_apply_creates_or_updates(api, tmp_path):
    routes, calls = api
    spec = tmp_path / "agente.json"
    spec.write_text(json.dumps({"agent_type": "suporte", "name": "Novo nome"}), encoding="utf-8")

    routes[("GET", "/agents")] = httpx.Response(200, json=[])
    routes[("POST", "/agents")] = httpx.Response(201, json=AGENT)
    assert _run("agents", "apply", "-f", str(spec)).exit_code == 0
    assert calls[-1].method == "POST"

    routes[("GET", "/agents")] = httpx.Response(200, json=[AGENT])
    routes[("PUT", "/agents/suporte")] = httpx.Response(200, json=AGENT)
    assert _run("agents", "apply", "-f", str(spec)).exit_code == 0
    assert calls[-1].method == "PUT" and json.loads(calls[-1].content) == {"name": "Novo nome"}


def test_delete_requires_yes_without_tty(api):
    assert _run("agents", "delete", "suporte").exit_code == 2


def _sse(*events: tuple[str, dict]) -> bytes:
    return "".join(f"event: {e}\r\ndata: {json.dumps(d)}\r\n\r\n" for e, d in events).encode()


def test_chat_missing_required_dependency_fails_without_prompt(api):
    routes, _ = api
    routes[("GET", "/agents/suporte")] = httpx.Response(200, json=AGENT)
    result = _run("--json", "chat", "suporte", "-m", "oi")
    assert result.exit_code == 2
    assert json.loads(result.stderr)["missing"] == ["cpf"]


def test_chat_streams_and_coerces_dependencies(api):
    routes, calls = api
    routes[("GET", "/agents/suporte")] = httpx.Response(200, json=AGENT)
    routes[("POST", "/chat/stream")] = httpx.Response(
        200,
        content=_sse(("run", {"run_id": "r1", "trace_id": "t1"}), ("message", {"content": "ol"}),
                     ("message", {"content": "á"}), ("done", {})),
        headers={"content-type": "text/event-stream"},
    )
    result = _run("--json", "chat", "suporte", "-m", "oi", "-d", "cpf=123")
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert (out["content"], out["run_id"]) == ("olá", "r1")
    body = json.loads(calls[-1].content)
    assert body["dependencies"] == {"cpf": "123"}  # string, como o agente declara

    # a sessão é reaproveitada na próxima mensagem
    _run("--json", "chat", "suporte", "-m", "de novo", "-d", "cpf=123")
    assert json.loads(calls[-1].content)["session_id"] == body["session_id"]


def test_chat_stream_error_event_exits_nonzero(api):
    routes, _ = api
    routes[("GET", "/agents/suporte")] = httpx.Response(200, json={**AGENT, "dependency_fields": []})
    routes[("POST", "/chat/stream")] = httpx.Response(
        200, content=_sse(("run", {"run_id": "r1"}), ("error", {"message": "modelo caiu"}), ("done", {}))
    )
    assert _run("chat", "suporte", "-m", "oi").exit_code == 1


def test_tool_invoke_ok_false_exits_nonzero(api):
    routes, _ = api
    routes[("POST", "/tools/calc/invoke")] = httpx.Response(200, json={"ok": False, "result": None, "error": "boom"})
    assert _run("tools", "invoke", "calc", "-a", "x=1").exit_code == 1
