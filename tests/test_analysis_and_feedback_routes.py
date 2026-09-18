"""`/analyze` e `/agents/{agent_type}/feedback` — chamando as funções da rota
direto (mesmo estilo de test_integration_contract.py), sem TestClient."""

import asyncio

import pytest
from fastapi import HTTPException

from agent_service.api.agents_routes import (
    AgentDefinitionIn,
    FeedbackIn,
    create_agent,
    delete_agent,
    get_feedback,
    send_feedback,
)
from agent_service.api.routes import AnalyzeRequest, analyze


@pytest.fixture
def conversational_agent():
    create_agent(AgentDefinitionIn(agent_type="rota_conv", name="Conv", instructions=["Seja breve."]))
    yield "rota_conv"
    delete_agent("rota_conv")


@pytest.fixture
def analysis_agent():
    create_agent(
        AgentDefinitionIn(
            agent_type="rota_analise",
            name="Análise",
            instructions=["Extraia os campos."],
            kind="analysis",
            response_schema=[{"name": "valor", "type": "number", "required": True}],
        )
    )
    yield "rota_analise"
    delete_agent("rota_analise")


def test_create_analysis_without_response_schema_is_422():
    with pytest.raises(HTTPException) as exc:
        create_agent(AgentDefinitionIn(agent_type="x", name="X", instructions=["a"], kind="analysis"))
    assert exc.value.status_code == 422


def test_create_conversational_with_response_schema_is_422():
    with pytest.raises(HTTPException) as exc:
        create_agent(
            AgentDefinitionIn(
                agent_type="x", name="X", instructions=["a"],
                response_schema=[{"name": "v", "type": "number"}],
            )
        )
    assert exc.value.status_code == 422


def test_analyze_unknown_agent_is_404():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(analyze(AnalyzeRequest(agent_type="nao-existe", document="doc")))
    assert exc.value.status_code == 404


def test_analyze_rejects_conversational_agent(conversational_agent):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(analyze(AnalyzeRequest(agent_type=conversational_agent, document="doc")))
    assert exc.value.status_code == 422


def test_chat_with_invalid_attachment_is_422(conversational_agent):
    from agent_service.agents.attachments import AttachmentIn
    from agent_service.api.routes import ChatRequest, chat

    request = ChatRequest(
        agent_type=conversational_agent,
        user_id="u",
        session_id="s",
        message="oi",
        attachments=[AttachmentIn(content_base64="AAAA", mime_type="application/x-desconhecido")],
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat(request))
    assert exc.value.status_code == 422


def test_analyze_with_invalid_attachment_is_422(analysis_agent):
    from agent_service.agents.attachments import AttachmentIn

    request = AnalyzeRequest(
        agent_type=analysis_agent,
        document="veja o anexo",
        attachments=[AttachmentIn(content_base64="AAAA", mime_type="application/x-desconhecido")],
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(analyze(request))
    assert exc.value.status_code == 422


def test_feedback_unknown_agent_404():
    with pytest.raises(HTTPException) as exc:
        get_feedback("nao-existe")
    assert exc.value.status_code == 404


def test_feedback_no_note_yet_404(conversational_agent):
    with pytest.raises(HTTPException) as exc:
        get_feedback(conversational_agent)
    assert exc.value.status_code == 404


def test_feedback_empty_session_is_422(conversational_agent):
    with pytest.raises(HTTPException) as exc:
        send_feedback(conversational_agent, FeedbackIn(session_id="sessao-vazia", feedback="seja mais direto"))
    assert exc.value.status_code == 422
