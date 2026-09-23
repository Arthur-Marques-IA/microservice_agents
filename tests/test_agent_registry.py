import pytest

from agent_service.agents.registry import UnknownAgentTypeError, get_agent, get_agent_with_definition, list_agent_types
from agent_service.agents.store import create_definition, delete_definition, save_feedback_note


def test_list_agent_types_includes_conversational():
    assert "conversational" in list_agent_types()


def test_get_agent_returns_same_cached_instance():
    agent_a = get_agent("conversational")
    agent_b = get_agent("conversational")
    assert agent_a is agent_b


def test_get_agent_unknown_type_raises():
    with pytest.raises(UnknownAgentTypeError):
        get_agent("does-not-exist")


def test_analysis_agent_gets_output_schema():
    create_definition(
        agent_type="teste-analista",
        name="Teste analista",
        instructions=["Extraia os campos."],
        kind="analysis",
        response_schema=[{"name": "valor", "type": "number", "required": True}],
    )
    try:
        agent, definition = get_agent_with_definition("teste-analista")
        assert definition["kind"] == "analysis"
        assert agent.output_schema is not None
        assert "valor" in agent.output_schema.model_fields
        assert agent.add_history_to_context is False
    finally:
        delete_definition("teste-analista")


def test_feedback_note_change_invalidates_cache():
    create_definition(agent_type="teste-feedback", name="Teste feedback", instructions=["Seja breve."])
    try:
        agent_before, _ = get_agent_with_definition("teste-feedback")
        save_feedback_note("teste-feedback", [{"id": "r1", "texto": "sempre cumprimente o cliente pelo nome"}])
        agent_after, _ = get_agent_with_definition("teste-feedback")
        assert agent_before is not agent_after
        assert any("sempre cumprimente" in i for i in agent_after.instructions)
    finally:
        delete_definition("teste-feedback")
