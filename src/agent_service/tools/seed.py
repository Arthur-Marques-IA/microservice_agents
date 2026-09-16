"""Semeia algumas tools de exemplo — uma de cada `kind` que já funciona sem
segredo nenhum — pra quem sobe o serviço do zero já ver o catálogo populado
em vez de uma tela vazia. Chamado uma vez no startup (`main.py`), depois de
`tools/store.py::init_store()`. Não sobrescreve o que já existe.

`web_search` (precisa do extra `tools`, ver README) fica de fora de
propósito: a tool apareceria pronta mas falharia ao construir sem o pacote
instalado — melhor o usuário criá-la quando tiver o extra.
"""

from agent_service.tools.store import create_tool_if_missing


def seed_default_tools() -> None:
    create_tool_if_missing(
        tool_name="calculator",
        kind="builtin",
        label="Calculadora",
        description=None,
        config={"builtin_id": "calculator", "params": {}},
        is_seed=True,
    )
    create_tool_if_missing(
        tool_name="hackernews",
        kind="builtin",
        label="Hacker News",
        description=None,
        config={"builtin_id": "hackernews", "params": {}},
        is_seed=True,
    )
    create_tool_if_missing(
        tool_name="cat_fact",
        kind="api",
        label="Fato aleatório sobre gatos",
        description="Devolve um fato curto e aleatório sobre gatos — exemplo de tool via API, sem parâmetros nem autenticação.",
        config={"method": "GET", "url": "https://catfact.ninja/fact", "parameters": []},
        is_seed=True,
    )
