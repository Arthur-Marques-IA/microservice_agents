"""Collections de documentos: cadastro dinâmico e o elo com os agentes
(`knowledge_collection`), que é o que dá ao agente uma tool de busca na base.
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from agent_service.agents.base import build_agent
from agent_service.api.agents_routes import (
    AgentDefinitionIn,
    AgentDefinitionUpdate,
    create_agent,
    delete_agent,
    update_agent,
)
from agent_service.api.collections_routes import (
    CollectionIn,
    CollectionUpdateIn,
    create_collection,
    delete_collection,
    get_collection_detail,
    list_collections,
    update_collection,
)
from agent_service.documents.collections import collection_exists


@pytest.fixture
def manuais():
    created = create_collection(CollectionIn(name="manuais", label="Manuais", description="PDFs do produto"))
    yield created["name"]
    if any(c["name"] == "manuais" for c in list_collections()):
        delete_collection("manuais")


def _agent(**extra):
    return AgentDefinitionIn(agent_type="agente_rag", name="RAG", instructions=["Consulte os manuais."], **extra)


# -- cadastro ---------------------------------------------------------------------


def test_seeded_collection_is_listed():
    assert "general" in [c["name"] for c in list_collections()]


def test_create_and_update_collection(manuais):
    assert collection_exists("manuais")
    assert get_collection_detail("manuais")["label"] == "Manuais"
    assert update_collection("manuais", CollectionUpdateIn(label="Manuais do produto"))["label"] == "Manuais do produto"


def test_duplicate_and_invalid_names_are_rejected(manuais):
    with pytest.raises(HTTPException) as exc:
        create_collection(CollectionIn(name="manuais", label="Outra"))
    assert exc.value.status_code == 409

    with pytest.raises(HTTPException) as exc:
        create_collection(CollectionIn(name="Com Espaço", label="x"))
    assert exc.value.status_code == 422


def test_seeded_collection_cannot_be_deleted():
    with pytest.raises(HTTPException) as exc:
        delete_collection("general")
    assert exc.value.status_code == 403


# -- elo com o agente ---------------------------------------------------------------


def test_agent_can_point_to_a_collection_and_gets_a_search_tool(manuais):
    created = create_agent(_agent(knowledge_collection="manuais"))
    try:
        assert created["knowledge_collection"] == "manuais"
        with patch("agent_service.agents.base.get_collection") as get_collection:
            agent = build_agent(agent_id="x", name="x", instructions=["x"], knowledge_collection="manuais")
        get_collection.assert_called_once_with("manuais")
        assert agent.knowledge is get_collection.return_value
        assert agent.search_knowledge is True
    finally:
        delete_agent("agente_rag")


def test_agent_without_collection_has_no_knowledge():
    agent = build_agent(agent_id="x", name="x", instructions=["x"])
    assert agent.knowledge is None and agent.search_knowledge is False


def test_unknown_collection_is_rejected_on_create_and_update(manuais):
    with pytest.raises(HTTPException) as exc:
        create_agent(_agent(knowledge_collection="nao-existe"))
    assert exc.value.status_code == 422

    create_agent(_agent(knowledge_collection="manuais"))
    try:
        with pytest.raises(HTTPException) as exc:
            update_agent("agente_rag", AgentDefinitionUpdate(knowledge_collection="nao-existe"))
        assert exc.value.status_code == 422
        # E dá para desligar a base voltando o campo para None.
        assert update_agent("agente_rag", AgentDefinitionUpdate(knowledge_collection=None))["knowledge_collection"] is None
    finally:
        delete_agent("agente_rag")


def test_collection_in_use_cannot_be_deleted(manuais):
    create_agent(_agent(knowledge_collection="manuais"))
    try:
        with pytest.raises(HTTPException) as exc:
            delete_collection("manuais")
        assert exc.value.status_code == 409
        assert "agente_rag" in exc.value.detail
        assert get_collection_detail("manuais")["agents_using"] == ["agente_rag"]
    finally:
        delete_agent("agente_rag")
