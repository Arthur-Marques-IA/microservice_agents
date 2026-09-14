"""Agente conversacional: atende diálogo geral com o usuário final.

Primeiro tipo de agente implementado ponta a ponta (ver roadmap para
orquestrador e analista).
"""

from agno.agent import Agent

from agent_service.agents.base import build_agent
from agent_service.config import get_settings
from agent_service.tools.registry import get_tools

AGENT_TYPE = "conversational"

INSTRUCTIONS = [
    "Você é um assistente conversacional da plataforma.",
    "Responda de forma direta e cordial, em português por padrão.",
    "Use o histórico e as memórias do usuário para manter contexto entre mensagens.",
]


def create_conversational_agent() -> Agent:
    memory_backend = "mem0" if get_settings().mem0_enabled else "common"
    return build_agent(
        agent_id=AGENT_TYPE,
        name="Agente Conversacional",
        instructions=INSTRUCTIONS,
        tools=get_tools(AGENT_TYPE),
        memory_backend=memory_backend,
    )
