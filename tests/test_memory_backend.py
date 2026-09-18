"""Um backend de memória de longo prazo por vez (`agents/base.py::build_agent`)."""

from agent_service.agents.base import build_agent
from agent_service.memory.mem0_hooks import mem0_post_hook, mem0_pre_hook


def test_common_backend_uses_agno_memory():
    agent = build_agent(agent_id="x", name="x", instructions=["x"], memory_backend="common")
    assert agent.memory_manager is not None
    assert agent.enable_agentic_memory is True
    assert agent.add_memories_to_context is True
    assert not agent.pre_hooks and not agent.post_hooks


def test_mem0_backend_replaces_agno_memory():
    agent = build_agent(agent_id="x", name="x", instructions=["x"], memory_backend="mem0")
    assert agent.memory_manager is None
    assert agent.enable_agentic_memory is False
    assert agent.add_memories_to_context is False
    assert agent.pre_hooks == [mem0_pre_hook]
    assert agent.post_hooks == [mem0_post_hook]
    # O histórico da sessão não é memória de longo prazo: continua ligado.
    assert agent.add_history_to_context is True


def test_analysis_has_no_memory_even_with_mem0():
    agent = build_agent(agent_id="x", name="x", instructions=["x"], memory_backend="mem0", kind="analysis")
    assert agent.memory_manager is None
    assert agent.enable_agentic_memory is False
    assert agent.add_memories_to_context is False
    assert not agent.pre_hooks and not agent.post_hooks
