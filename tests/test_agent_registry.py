import pytest

from agent_service.agents.registry import UnknownAgentTypeError, get_agent, list_agent_types


def test_list_agent_types_includes_conversational():
    assert "conversational" in list_agent_types()


def test_get_agent_returns_same_cached_instance():
    agent_a = get_agent("conversational")
    agent_b = get_agent("conversational")
    assert agent_a is agent_b


def test_get_agent_unknown_type_raises():
    with pytest.raises(UnknownAgentTypeError):
        get_agent("does-not-exist")
