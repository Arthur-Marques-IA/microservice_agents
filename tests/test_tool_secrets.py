"""Segredo de tool não aparece em leitura nenhuma, nem volta ao modelo.

O caso que motivou: o `tool_get` do MCP devolveu em texto puro o `X-Regente-Token` guardado
em `headers` — só o `auth` era mascarado — e trocar o token exigia digitá-lo no `tool_apply`.
"""

import asyncio

import httpx
import pytest
from fastapi import HTTPException

from agent_service.api.secrets_routes import SecretIn, delete_secret, list_secrets, set_secret
from agent_service.api.tools_routes import (
    ToolIn,
    ToolInvokeIn,
    ToolUpdateIn,
    create_tool,
    delete_tool,
    get_tool,
    list_tools,
    update_tool,
)
from agent_service.api.tools_routes import invoke_tool as invocar
from agent_service.tools import api_tool
from agent_service.tools import secrets as secrets_store
from agent_service.tools.python_tool import compile_python_tool, validate_python_config
from agent_service.tools.sensitive import SECRET_MASK, is_sensitive

TOKEN = "tok-regente-9f8e7d6c5b4a"


def _config(header_value=TOKEN, **extra):
    return {
        "method": "GET",
        "url": "https://exemplo.test/ficha",
        "headers": {"X-Regente-Token": header_value, "Accept": "application/json"},
        "parameters": [
            {"name": "api_key", "type": "string", "location": "query", "source": "const", "value": "chave-fixa-123"},
            {"name": "cpf", "type": "string", "location": "query", "required": True},
        ],
        **extra,
    }


@pytest.fixture
def rede():
    """A API falsa devolve os headers e a query que recebeu — muita API real faz isso."""
    recebidas: list[httpx.Request] = []

    def handler(request):
        recebidas.append(request)
        return httpx.Response(
            200, json={"eco_header": request.headers.get("X-Regente-Token"), "eco_query": str(request.url)}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    original = api_tool.get_client
    api_tool.get_client = lambda: client
    try:
        yield recebidas
    finally:
        api_tool.get_client = original


@pytest.fixture
def ficha():
    create_tool(ToolIn(tool_name="ficha_regente", kind="api", label="Ficha", config=_config(), side_effect=False))
    yield "ficha_regente"
    delete_tool("ficha_regente")


@pytest.fixture
def segredo():
    set_secret("REGENTE_TOKEN", SecretIn(value=TOKEN))
    yield "REGENTE_TOKEN"
    secrets_store.delete_secret("REGENTE_TOKEN")


def test_nomes_sensiveis():
    for name in ("X-Regente-Token", "api_key", "X-API-Key", "Authorization", "client_secret", "Cookie", "key"):
        assert is_sensitive(name), name
    for name in ("Accept", "Idempotency-Key-Id", "cpf", "monkey", "X-Request-Id"):
        assert not is_sensitive(name), name


def test_header_e_parametro_fixo_sensiveis_saem_mascarados(ficha):
    lida = get_tool(ficha)
    assert lida["config"]["headers"] == {"X-Regente-Token": SECRET_MASK, "Accept": "application/json"}
    assert lida["config"]["parameters"][0]["value"] == SECRET_MASK
    assert TOKEN not in str(list_tools()) and "chave-fixa-123" not in str(list_tools())


def test_devolver_a_mascara_mantem_o_valor_guardado(ficha):
    """Quem lê a tool e a devolve editando outra coisa não pode apagar o token."""
    config = get_tool(ficha)["config"]
    config["headers"]["Accept"] = "text/plain"
    update_tool(ficha, ToolUpdateIn(config=config))
    from agent_service.tools import store

    guardada = store.get_tool(ficha)["config"]
    assert guardada["headers"]["X-Regente-Token"] == TOKEN
    assert guardada["parameters"][0]["value"] == "chave-fixa-123"


def test_mascara_sem_valor_para_restaurar_e_recusada(ficha):
    config = get_tool(ficha)["config"]
    config["headers"]["X-Outro-Token"] = config["headers"].pop("X-Regente-Token")  # renomeado com a máscara
    with pytest.raises(HTTPException) as erro:
        update_tool(ficha, ToolUpdateIn(config=config))
    assert erro.value.status_code == 422 and "secret" in erro.value.detail
    # Criar outra tool a partir da leitura (ex.: copiar de um ambiente para outro) também.
    with pytest.raises(HTTPException) as erro:
        create_tool(ToolIn(tool_name="ficha_copia", kind="api", label="Cópia", config=get_tool(ficha)["config"]))
    assert erro.value.status_code == 422


def test_referencia_a_segredo_que_nao_existe_e_recusada():
    with pytest.raises(HTTPException) as erro:
        create_tool(ToolIn(tool_name="ficha_ref", kind="api", label="x", config=_config("{{secret:NAO_EXISTE}}")))
    assert erro.value.status_code == 422 and "kuro secrets set NAO_EXISTE" in erro.value.detail


def test_referencia_resolve_na_chamada_e_nao_volta_ao_modelo(rede, segredo):
    create_tool(ToolIn(tool_name="ficha_ref", kind="api", label="x", config=_config("{{secret:REGENTE_TOKEN}}"), side_effect=False))
    try:
        # A leitura mostra a referência, não o valor (e não a mascara: não é segredo).
        assert get_tool("ficha_ref")["config"]["headers"]["X-Regente-Token"] == "{{secret:REGENTE_TOKEN}}"
        out = asyncio.run(invocar("ficha_ref", ToolInvokeIn(arguments={"cpf": "1"})))
        assert rede[-1].headers["X-Regente-Token"] == TOKEN
        assert "api_key=chave-fixa-123" in str(rede[-1].url)
        # A API ecoou o token e a URL com a chave: nada disso volta ao modelo.
        assert TOKEN not in out["result"] and "chave-fixa-123" not in out["result"]

        # Trocar o valor vale na próxima chamada, sem mexer na tool.
        set_secret("REGENTE_TOKEN", SecretIn(value="tok-novo-0000"))
        asyncio.run(invocar("ficha_ref", ToolInvokeIn(arguments={"cpf": "1"})))
        assert rede[-1].headers["X-Regente-Token"] == "tok-novo-0000"

        # Em uso, o segredo não pode ser removido.
        with pytest.raises(HTTPException) as erro:
            delete_secret("REGENTE_TOKEN")
        assert erro.value.status_code == 409 and "ficha_ref" in erro.value.detail
        assert [s for s in list_secrets() if s["name"] == "REGENTE_TOKEN"][0]["used_by"] == ["ficha_ref"]
    finally:
        delete_tool("ficha_ref")


def test_listar_segredos_nunca_mostra_o_valor(segredo):
    listado = list_secrets()
    assert any(s["name"] == segredo for s in listado)
    assert TOKEN not in str(listado)
    assert set_secret(segredo, SecretIn(value=TOKEN))["hint"].endswith("4a")


def test_segredo_removido_vira_erro_de_configuracao_da_tool(rede):
    set_secret("TEMPORARIO", SecretIn(value="valor-temporario"))
    create_tool(ToolIn(tool_name="ficha_tmp", kind="api", label="x", config=_config("{{secret:TEMPORARIO}}"), side_effect=False))
    try:
        secrets_store.delete_secret("TEMPORARIO")  # por fora da rota, que barraria
        out = asyncio.run(invocar("ficha_tmp", ToolInvokeIn(arguments={"cpf": "1"})))
        assert out["ok"] is False and out["failure"] == "config" and "TEMPORARIO" in out["result"]
        assert rede == []
    finally:
        delete_tool("ficha_tmp")


def test_tool_python_le_o_segredo_sem_ele_aparecer_no_codigo(segredo):
    code = "def ler() -> str:\n    return secret('REGENTE_TOKEN')[:4]\n"
    fn = compile_python_tool(
        tool_name="ler", config=validate_python_config({"code": code, "entrypoint": "ler"}), enabled=True
    )
    assert fn() == TOKEN[:4]
