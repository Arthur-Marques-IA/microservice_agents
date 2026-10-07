"""Num teste (`dry_run`), tool com efeito colateral só roda se declara que trata o teste.

O caso que motivou: as tools do Regente ignoravam o `X-Kuro-Dry-Run`, e um teste "seguro"
pelo MCP teria gravado lead e ficha em produção. Aqui, pelos dois caminhos: o teste de
tool (`invoke_tool`) e o run de um agente, passando pela cadeia de hooks do próprio Agno."""

import asyncio

import httpx
import pytest
from agno.agent import Agent
from agno.agent._tools import parse_tools
from agno.models.openai import OpenAIChat
from agno.tools.function import FunctionCall
from pydantic import ValidationError

from agent_service.api.tools_routes import ToolIn, ToolInvokeIn, ToolUpdateIn, create_tool, delete_tool, update_tool
from agent_service.api.tools_routes import invoke_tool as invocar
from agent_service.tools import api_tool, registry
from agent_service.tools.context import dependencies_scope

CONFIG = {
    "method": "POST",
    "url": "https://exemplo.test/leads",
    "parameters": [{"name": "nome", "type": "string", "location": "body", "required": True}],
}


@pytest.fixture
def rede():
    chamadas: list[httpx.Request] = []

    def handler(request):
        chamadas.append(request)
        return httpx.Response(201, json={"id": 7})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    original = api_tool.get_client
    api_tool.get_client = lambda: client
    try:
        yield chamadas
    finally:
        api_tool.get_client = original


@pytest.fixture
def gravar_lead():
    create_tool(ToolIn(tool_name="gravar_lead", kind="api", label="Gravar lead", config=CONFIG, side_effect=True))
    yield "gravar_lead"
    delete_tool("gravar_lead")


def _invoke(tool, dry_run=True):
    return asyncio.run(invocar(tool, ToolInvokeIn(arguments={"nome": "Ana"}, dry_run=dry_run)))


def test_efeito_colateral_sem_suporte_nao_e_chamada_no_teste(rede, gravar_lead):
    out = _invoke(gravar_lead)
    assert rede == []
    assert out["ok"] is True and out["dry_run_skipped"] is True
    assert "não foi chamada" in out["result"] and '"nome": "Ana"' in out["result"]
    assert "dry_run_support=true" in out["result"]  # diz como resolver


def test_fora_do_teste_a_tool_roda_normalmente(rede, gravar_lead):
    out = _invoke(gravar_lead, dry_run=False)
    assert len(rede) == 1 and out["dry_run_skipped"] is False


def test_declarando_suporte_ela_roda_no_teste_com_o_header(rede, gravar_lead):
    update_tool(gravar_lead, ToolUpdateIn(dry_run_support=True))
    out = _invoke(gravar_lead)
    assert out["dry_run_skipped"] is False
    assert rede[0].headers["X-Kuro-Dry-Run"] == "true"


def test_nao_classificada_tambem_nao_roda_e_so_leitura_roda(rede, gravar_lead):
    update_tool(gravar_lead, ToolUpdateIn(side_effect=None))
    assert _invoke(gravar_lead)["dry_run_skipped"] is True
    assert "não foi classificada" in _invoke(gravar_lead)["result"]
    update_tool(gravar_lead, ToolUpdateIn(side_effect=False))
    assert _invoke(gravar_lead)["dry_run_skipped"] is False and len(rede) == 1


def test_builtin_nao_pode_declarar_suporte():
    """Uma toolkit do Agno não recebe o header: declarar suporte seria mentira."""
    with pytest.raises(ValidationError):
        ToolIn(tool_name="mail", kind="builtin", label="x", config={"builtin_id": "calculator"}, dry_run_support=True)


# -- no run de um agente: a cadeia de hooks do Agno -----------------------------------


def _functions(names):
    """As funções como o Agno as prepara para um run assíncrono, com o hook do agente."""
    tools, _, hook = registry.resolve_for_agent(names)
    agent = Agent(tools=tools, tool_hooks=[hook] if hook else None)
    model = OpenAIChat(id="gpt-teste", api_key="sk-teste")
    return {f.name: f for f in parse_tools(agent, tools, model, async_mode=True)}, hook


async def _call(function, arguments, dry_run):
    with dependencies_scope({}, dry_run=dry_run):
        call = FunctionCall(function=function, arguments=arguments)
        await call.aexecute()
        return call.result


def test_no_run_do_agente_o_hook_barra_api_e_toolkit(rede, gravar_lead):
    create_tool(ToolIn(tool_name="calc_nao_classificada", kind="builtin", label="Calc", config={"builtin_id": "calculator"}))
    try:
        functions, hook = _functions([gravar_lead, "calc_nao_classificada"])
        assert hook is not None
        barrada = asyncio.run(_call(functions["gravar_lead"], {"nome": "Ana"}, dry_run=True))
        assert rede == [] and "não foi chamada" in str(barrada)
        # Uma função de toolkit (builtin) também passa pelo hook.
        soma = asyncio.run(_call(functions["add"], {"a": 1, "b": 2}, dry_run=True))
        assert "não foi chamada" in str(soma)
        # Fora do teste, a mesma função roda.
        asyncio.run(_call(functions["gravar_lead"], {"nome": "Ana"}, dry_run=False))
        assert len(rede) == 1
    finally:
        delete_tool("calc_nao_classificada")


def test_sem_tool_barrada_o_agente_fica_sem_hook(gravar_lead):
    update_tool(gravar_lead, ToolUpdateIn(side_effect=False))
    _, hook = _functions([gravar_lead])
    assert hook is None


def test_agente_do_registry_traz_o_hook_e_perde_quando_a_tool_e_classificada(gravar_lead):
    """O caminho de produção: o `/chat` pega o agente do registry, não um `Agent` montado
    à mão. Classificar a tool muda o `updated_at` dela, e o agente em cache é refeito."""
    from agent_service.agents.registry import get_agent
    from agent_service.agents.store import create_definition, delete_definition

    create_definition(agent_type="usa-gravar-lead", name="Usa", instructions=["oi"], tools=[gravar_lead])
    try:
        agente = get_agent("usa-gravar-lead")
        assert agente.tool_hooks and agente.tool_hooks[0].__name__ == "kuro_dry_run_guard"
        update_tool(gravar_lead, ToolUpdateIn(side_effect=False))
        assert get_agent("usa-gravar-lead").tool_hooks is None
    finally:
        delete_definition("usa-gravar-lead")
