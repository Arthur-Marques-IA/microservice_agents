"""Quem pode chamar o quê — chave de API com dois escopos.

Sem isto, todo vizinho de rede que alcança a porta consegue ler qualquer
conversa que passou pelo serviço (`GET /observability/runs`, `/sessions`),
reescrever o prompt de um agente em produção (`PUT /agents/{t}`) e ler as
credenciais de modelo cadastradas. Não é hipótese: nenhuma rota exigia
credencial nenhuma.

Dois escopos, porque são dois públicos com riscos diferentes:

- `runtime`: só executa — `/chat`, `/chat/stream`, `/analyze` e registrar score.
  É a chave que vai para o outro módulo da plataforma. Se vazar, o estrago é
  gastar tokens, não ler o histórico de todo mundo nem trocar o prompt.
- `admin`: todo o resto — CRUD de agentes, tools, credenciais, collections,
  leitura de traces e de sessões. É a chave do console e da CLI.

**Middleware e não `Depends` por rota** de propósito: o AgentOS monta rotas
próprias por cima deste app (`/sessions`, `/knowledge/...`), e elas expõem
conversa. Uma dependência por router deixaria justamente essas de fora, que é o
tipo de falha que não aparece em teste de rota nenhuma.

As chaves vêm do ambiente (`ADMIN_API_KEY`, `RUNTIME_API_KEY`), não de uma
tabela. Para um piloto com um cliente, é o tamanho certo: rotacionar é trocar a
variável e reiniciar. Várias chaves, com revogação e `last_used_at`, é o passo
seguinte (ROADMAP H0) e precisa de tabela e CRUD.

**Sem nenhuma chave configurada, o serviço fica aberto** — é o comportamento de
antes, para não quebrar quem já roda local. `GET /health` avisa, e `kuro health`
mostra em vermelho. Em qualquer ambiente compartilhado, configure as duas.
"""

import secrets
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_service.config import get_settings

Scope = Literal["runtime", "admin"]

PUBLIC_PATHS = frozenset({"/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"})
"""Aberto sempre. `/health` precisa estar: é o healthcheck do container e de
qualquer load balancer na frente."""

RUNTIME_PATHS = frozenset({"/chat", "/chat/stream", "/analyze", "/observability/scores"})
"""O que a chave `runtime` alcança — executar um agente e avaliar a execução.
Tudo que não está aqui (nem em PUBLIC_PATHS) exige `admin`."""


def configured_keys() -> dict[Scope, str]:
    settings = get_settings()
    chaves: dict[Scope, str] = {}
    if settings.admin_api_key:
        chaves["admin"] = settings.admin_api_key
    if settings.runtime_api_key:
        chaves["runtime"] = settings.runtime_api_key
    return chaves


def auth_enabled() -> bool:
    return bool(configured_keys())


def _presented_key(request: Request) -> str | None:
    """Aceita `Authorization: Bearer <chave>` ou `X-API-Key: <chave>` — o
    primeiro é o que a maioria dos clientes HTTP já sabe mandar."""
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return request.headers.get("x-api-key") or None


def _scope_of(key: str) -> Scope | None:
    """`compare_digest` em vez de `==`: comparação de segredo não deve vazar,
    pelo tempo de resposta, quantos caracteres bateram."""
    for scope, valor in configured_keys().items():
        if secrets.compare_digest(key, valor):
            return scope
    return None


def required_scope(path: str) -> Scope | None:
    """`None` = rota aberta."""
    if path in PUBLIC_PATHS:
        return None
    return "runtime" if path in RUNTIME_PATHS else "admin"


def _authorized(presented: Scope | None, needed: Scope) -> bool:
    # `admin` faz tudo que `runtime` faz; o contrário não.
    return presented == "admin" or presented == needed


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def api_key_middleware(request: Request, call_next):  # noqa: ANN001, ANN202
        if not auth_enabled():
            return await call_next(request)

        needed = required_scope(request.url.path)
        if needed is None:
            return await call_next(request)

        key = _presented_key(request)
        if key is None:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Esta rota exige uma chave de API. Mande "
                    "`Authorization: Bearer <chave>` ou `X-API-Key: <chave>`."
                },
            )
        scope = _scope_of(key)
        if scope is None or not _authorized(scope, needed):
            # Mesma resposta para chave inválida e para escopo insuficiente:
            # dizer "a chave é válida, mas não aqui" já entrega informação.
            return JSONResponse(
                status_code=403,
                content={"detail": f"Chave sem permissão para esta rota (exige escopo {needed!r})."},
            )
        return await call_next(request)
