"""`/analyze` e `/agents/{agent_type}/feedback` — chamando as funções da rota
direto (mesmo estilo de test_integration_contract.py), sem TestClient."""

import asyncio

import pytest
from fastapi import HTTPException

from agent_service.api.agents_routes import (
    AgentDefinitionIn,
    AgentDefinitionUpdate,
    FeedbackIn,
    create_agent,
    delete_agent,
    get_feedback,
    send_feedback,
    update_agent,
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


# -- response_schema com tipos compostos, pela rota ------------------------------


def test_create_analysis_com_array_de_objetos():
    criado = create_agent(
        AgentDefinitionIn(
            agent_type="rota_parcelas",
            name="Parcelas",
            instructions=["Extraia as parcelas."],
            kind="analysis",
            response_schema=[
                {
                    "name": "parcelas",
                    "type": "array",
                    "required": True,
                    "items": {
                        "type": "object",
                        "fields": [{"name": "numero", "type": "integer", "required": True}],
                    },
                }
            ],
        )
    )
    try:
        campo = criado["response_schema"][0]
        assert campo["type"] == "array"
        assert campo["items"]["fields"][0]["name"] == "numero"
    finally:
        delete_agent("rota_parcelas")


def test_create_analysis_com_object_sem_fields_e_422():
    with pytest.raises(HTTPException) as exc:
        create_agent(
            AgentDefinitionIn(
                agent_type="rota_ruim", name="Ruim", instructions=["a"], kind="analysis",
                response_schema=[{"name": "cliente", "type": "object"}],
            )
        )
    assert exc.value.status_code == 422
    assert "fields" in str(exc.value.detail)


# -- campos que não fazem nada em analysis ---------------------------------------


def test_create_analysis_com_num_history_runs_e_422():
    with pytest.raises(HTTPException) as exc:
        create_agent(
            AgentDefinitionIn(
                agent_type="rota_inerte", name="X", instructions=["a"], kind="analysis",
                num_history_runs=5,
                response_schema=[{"name": "v", "type": "number"}],
            )
        )
    assert exc.value.status_code == 422
    assert "num_history_runs" in str(exc.value.detail)


def test_create_analysis_com_mem0_e_422():
    with pytest.raises(HTTPException) as exc:
        create_agent(
            AgentDefinitionIn(
                agent_type="rota_inerte2", name="X", instructions=["a"], kind="analysis",
                memory_backend="mem0",
                response_schema=[{"name": "v", "type": "number"}],
            )
        )
    assert exc.value.status_code == 422
    assert "memory_backend" in str(exc.value.detail)


def test_update_de_analysis_sem_tocar_nos_inertes_passa(analysis_agent):
    """O agente salvo já carrega `num_history_runs=10` por default. Cobrar isso no
    merge faria um PUT de instructions falhar por um campo que ninguém escreveu."""
    atualizado = update_agent(analysis_agent, AgentDefinitionUpdate(instructions=["Outra instrução."]))
    assert atualizado["instructions"] == ["Outra instrução."]


# -- feedback não se aplica a agente analysis ------------------------------------


def test_feedback_em_agente_analysis_e_422(analysis_agent):
    """A nota só entra nas instructions de agente conversacional: aceitar aqui
    gravaria algo que nunca seria aplicado."""
    with pytest.raises(HTTPException) as exc:
        send_feedback(analysis_agent, FeedbackIn(session_id="s", feedback="seja mais direto"))
    assert exc.value.status_code == 422
    assert "analysis" in str(exc.value.detail)

    with pytest.raises(HTTPException) as exc:
        get_feedback(analysis_agent)
    assert exc.value.status_code == 422


# -- texto de entrada tem teto ----------------------------------------------------


def test_analyze_com_documento_gigante_e_422(analysis_agent):
    from agent_service.config import get_settings

    grande = "x" * (get_settings().max_input_chars + 1)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(analyze(AnalyzeRequest(agent_type=analysis_agent, document=grande)))
    assert exc.value.status_code == 422
    assert "caracteres" in str(exc.value.detail)


def test_chat_com_mensagem_gigante_e_422(conversational_agent):
    from agent_service.api.routes import ChatRequest, chat
    from agent_service.config import get_settings

    grande = "x" * (get_settings().max_input_chars + 1)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat(ChatRequest(agent_type=conversational_agent, user_id="u", session_id="s", message=grande)))
    assert exc.value.status_code == 422


# -- analysis é one-shot: não grava sessão ----------------------------------------


def test_agente_analysis_nao_persiste_sessao(analysis_agent):
    """Cada /analyze criaria uma linha `analyze-<uuid>` no Postgres com o documento
    inteiro dentro, que ninguém lê depois — o trace já registra tudo."""
    from agent_service.agents.registry import get_agent_with_definition

    agente, _ = get_agent_with_definition(analysis_agent)
    assert agente.db is None


def test_agente_conversacional_continua_persistindo(conversational_agent):
    from agent_service.agents.registry import get_agent_with_definition

    agente, _ = get_agent_with_definition(conversational_agent)
    assert agente.db is not None


def test_analysis_com_collection_mantem_a_busca(monkeypatch):
    """Tirar o `db` não pode levar o RAG junto: a collection tem o banco dela e a
    tool de busca do Agno não usa `agent.db`.

    Monta o agente direto, com a collection substituída: montar de verdade exigiria
    pgvector, que o ambiente de teste (sqlite) não tem."""
    from agent_service.agents import base

    colecao = object()
    monkeypatch.setattr(base, "get_collection", lambda nome: colecao)
    agente = base.build_agent(
        agent_id="a", name="A", instructions=["Extraia."], kind="analysis",
        knowledge_collection="manuais",
    )
    assert agente.db is None  # continua sem persistir sessão
    assert agente.knowledge is colecao
    assert agente.search_knowledge is True
