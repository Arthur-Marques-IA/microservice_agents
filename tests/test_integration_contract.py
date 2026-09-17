"""Contrato de integração: o que outro módulo precisa mandar para falar com o agente.

O ponto do endpoint é ser derivado — as dependências obrigatórias saem da
definição do agente e das tools que as consomem, não de um exemplo escrito à mão.
"""

import pytest
from fastapi import HTTPException

from agent_service.api.agents_routes import AgentDefinitionIn, create_agent, delete_agent
from agent_service.api.integration_routes import get_integration_contract
from agent_service.api.tools_routes import ToolIn, create_tool, delete_tool

TOOL_CONFIG = {
    "method": "GET",
    "url": "https://exemplo.test/clientes/{cpf}",
    "parameters": [
        {"name": "cpf", "type": "string", "location": "path", "required": True,
         "source": "dependency", "dependency": "cpf"},
    ],
}


@pytest.fixture
def agente():
    create_tool(ToolIn(tool_name="ficha_int", kind="api", label="Ficha", config=TOOL_CONFIG))
    create_agent(
        AgentDefinitionIn(
            agent_type="agente_int",
            name="Integração",
            instructions=["Ajude."],
            tools=["ficha_int"],
            dependency_fields=[
                {"name": "cpf", "type": "string", "required": True, "description": "CPF do cliente"},
                {"name": "vip", "type": "boolean", "required": False},
            ],
        )
    )
    yield "agente_int"
    delete_agent("agente_int")
    delete_tool("ficha_int")


def test_contract_says_who_needs_each_dependency(agente):
    contrato = get_integration_contract(agente, base_url="https://api.exemplo.com")

    cpf = next(d for d in contrato.dependencies if d.name == "cpf")
    assert cpf.required is True
    assert cpf.required_by_tools == ["ficha_int"], "o campo é exigido pela tool, não só declarado"
    assert contrato.warnings == []


def test_example_and_urls_use_the_given_base_url(agente):
    contrato = get_integration_contract(agente, base_url="https://api.exemplo.com/")

    assert contrato.chat_url == "https://api.exemplo.com/chat"
    assert contrato.stream_url == "https://api.exemplo.com/chat/stream"
    assert contrato.request_example["dependencies"]["cpf"] == "texto"
    assert "curl -X POST https://api.exemplo.com/chat" in contrato.curl
    assert '"agent_type": "agente_int"' in contrato.curl


def test_unknown_agent_is_404():
    with pytest.raises(HTTPException) as exc:
        get_integration_contract("nao-existe", base_url="http://x")
    assert exc.value.status_code == 404
