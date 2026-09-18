"""Agente de merge de feedback: transforma "não gostei disso, queria que
respondesse assim" numa nota de comportamento (markdown) persistida por
agente — `registry.py` concatena essa nota nas `instructions` em runtime.

Não é um agente configurável pelo usuário (sem tools, sem sessão, sem
`agent_definitions`): existe só para essa tarefa determinística de merge, com
instructions fixas — igual em espírito a `build_agent`, mas fora do CRUD.
"""

from agno.agent import Agent

from agent_service.agents.store import get_feedback_note, upsert_feedback_note
from agent_service.models.provider import get_model

_INSTRUCTIONS = [
    "Você mantém um documento markdown curto e objetivo com diretrizes de "
    "comportamento para um agente de IA de atendimento.",
    "Você recebe: (1) as notas atuais desse agente, (2) um trecho de uma "
    "conversa recente dele, e (3) um feedback textual de um humano sobre o "
    "que não gostou nessa conversa.",
    "Produza a versão atualizada COMPLETA das notas, mesclando o novo "
    "feedback com as regras já existentes.",
    "Nunca duplique uma regra já coberta; se o novo feedback a refina, "
    "reescreva-a. Remova ou ajuste regras que o novo feedback contradiz.",
    "Seja específico e acionável (ex.: 'Sempre confirme o CPF antes de dar "
    "detalhes da conta' em vez de 'seja mais cuidadoso').",
    "Formato: lista com marcadores (bullet points), sem títulos, sem "
    "nenhum comentário seu sobre o que mudou — responda só com o markdown "
    "final das notas, nada mais.",
]

_agent: Agent | None = None


def _merge_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(
            id="feedback-merge",
            name="Feedback merge",
            model=get_model(provider=None, model_id=None, credential_id=None),
            instructions=_INSTRUCTIONS,
            markdown=False,
        )
    return _agent


def _prompt(current_notes: str, transcript: str, feedback: str) -> str:
    return (
        f"Notas atuais:\n{current_notes or '(vazio)'}\n\n"
        f"Trecho da conversa:\n{transcript}\n\n"
        f"Feedback do usuário sobre essa conversa:\n{feedback}"
    )


def merge_feedback(agent_type: str, *, feedback: str, transcript: str) -> str:
    current = get_feedback_note(agent_type)
    result = _merge_agent().run(_prompt(current["content"] if current else "", transcript, feedback))
    content = (result.content or "").strip()
    upsert_feedback_note(agent_type, content)
    return content
