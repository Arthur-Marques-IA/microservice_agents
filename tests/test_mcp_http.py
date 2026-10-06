"""O MCP em `/mcp` (Streamable HTTP), num uvicorn de verdade: o lifespan do gerenciador
de sessões só roda assim, e é ele que um `mount` esquecido deixa de fora."""

import json
import socket
import threading
import time

import httpx
import pytest

pytest.importorskip("mcp")

import httpx2  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from mcp import Client as McpClient  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402
from mcp_types import ElicitResult  # noqa: E402

from agent_service.api import auth, mcp_routes  # noqa: E402
from agent_service.cli.client import Client  # noqa: E402
from agent_service.config import get_settings  # noqa: E402

ADMIN = "chave-admin"
RUNTIME = "chave-runtime"
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "teste", "version": "0"}},
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

# O conftest troca o DNS do processo inteiro por um IP público falso; aqui a conexão é
# de verdade, com o uvicorn em 127.0.0.1.
pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("resolvedor_real")]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def service():
    """O app com o middleware de chave e o `/mcp`, e uma API falsa atrás das tools."""
    settings = get_settings()
    saved = (settings.admin_api_key, settings.runtime_api_key)
    settings.admin_api_key, settings.runtime_api_key = ADMIN, RUNTIME
    calls: list[httpx.Request] = []

    def api(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "version": "9.9.9", "auth": "enabled"})
        if request.method == "GET" and request.url.path == "/agents/suporte":
            return httpx.Response(200, json={"agent_type": "suporte", "name": "Suporte", "is_seed": False})
        if request.method == "DELETE" and request.url.path == "/agents/suporte":
            return httpx.Response(204)
        return httpx.Response(404, json={"detail": "não encontrado"})

    original = mcp_routes._internal_client
    mcp_routes._internal_client = lambda: Client("http://kuro.interno", transport=httpx.MockTransport(api))
    try:
        route, lifespan = mcp_routes.build()
    finally:
        mcp_routes._internal_client = original
    app = FastAPI(lifespan=lifespan)
    app.router.routes.append(route)
    auth.install(app)

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started, "o uvicorn do teste não subiu"
    yield f"http://127.0.0.1:{port}/mcp", calls
    server.should_exit = True
    thread.join(timeout=5)
    settings.admin_api_key, settings.runtime_api_key = saved


def _client(url: str, key: str, **kwargs) -> McpClient:
    # Host de fora, como chega pelo Caddy: a checagem de Host do SDK aceitaria só localhost.
    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {key}", "Host": "kuro.example.com"}, timeout=30)
    return McpClient(streamable_http_client(url, http_client=http), **kwargs)


def _text(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)


def test_mcp_exige_a_chave_admin(service):
    url, _ = service
    assert httpx.post(url, json=INITIALIZE, headers=MCP_HEADERS).status_code == 401
    runtime = httpx.post(url, json=INITIALIZE, headers={**MCP_HEADERS, "Authorization": f"Bearer {RUNTIME}"})
    assert runtime.status_code == 403


def test_post_em_mcp_responde_sem_redirect(service):
    """Um 307 para `/mcp/` quebraria cliente que não segue redirect de POST."""
    url, _ = service
    response = httpx.post(url, json=INITIALIZE, headers={**MCP_HEADERS, "Authorization": f"Bearer {ADMIN}"})
    assert response.status_code == 200
    assert response.headers.get("mcp-session-id")


async def test_tools_chegam_na_api_pelo_cliente_interno(service):
    url, calls = service
    async with _client(url, ADMIN) as mcp:
        tools = {t.name for t in (await mcp.list_tools()).tools}
        result = await mcp.call_tool("health", {})
    assert {"health", "agents_list", "chat", "agent_delete"} <= tools
    assert not result.is_error, _text(result)
    data = result.structured_content or json.loads(result.content[0].text)
    assert data["service"]["version"] == "9.9.9"
    assert any(r.url.path == "/health" for r in calls)


async def test_nao_le_arquivo_do_servidor(service):
    """Pelo `/mcp`, um caminho seria do container: ler o `.env` ou o environ dele
    transformaria a chave admin nos segredos do serviço."""
    url, calls = service
    before = len(calls)
    async with _client(url, ADMIN) as mcp:
        result = await mcp.call_tool("collection_add", {"name": "manuais", "file": "/proc/self/environ"})
        analyze = await mcp.call_tool("eval", {"agent_type": "x", "cases_file": "/app/.env"})
    assert result.is_error and "inline" in _text(result)
    assert analyze.is_error and "inline" in _text(analyze)
    assert len(calls) == before


@pytest.mark.parametrize("mode", ["legacy", "auto"])
async def test_confirmacao_funciona_pelo_http(service, mode):
    """Remover pede confirmação no meio da tool: a resposta do cliente precisa achar a
    sessão de volta, o que só funciona com o servidor guardando a sessão."""
    url, calls = service
    asked: list[str] = []

    async def confirm(context, params):
        asked.append(params.message)
        return ElicitResult(action="accept", content={"confirmar": True})

    async with _client(url, ADMIN, mode=mode, elicitation_callback=confirm) as mcp:
        result = await mcp.call_tool("agent_delete", {"agent_type": "suporte"})
    assert not result.is_error, _text(result)
    assert asked and "suporte" in asked[0]
    assert any(r.method == "DELETE" and r.url.path == "/agents/suporte" for r in calls)
