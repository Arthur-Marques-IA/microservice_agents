"""Agente conversacional: definição original, usada só como seed.

Desde que a resolução de agentes passou a ser dinâmica (`agents/registry.py`
lê de `agents/store.py`), este módulo não constrói mais um `Agent` — só
expõe as constantes que `agents/seed.py` usa pra semear a primeira linha em
`agent_definitions` no startup, se ela ainda não existir.
"""

AGENT_TYPE = "conversational"

INSTRUCTIONS = [
    "Você é um assistente conversacional da plataforma.",
    "Responda de forma direta e cordial, em português por padrão.",
    "Use o histórico e as memórias do usuário para manter contexto entre mensagens.",
]
