"""Ponto de entrada do microserviço.

Monta um FastAPI próprio com o contrato estável (`agent_service.api.routes`)
e o passa como `base_app` para o `AgentOS` do Agno, que adiciona por cima as
rotas nativas de execução/streaming de agentes, sessões e tracing (usadas
pelo playground em os.agno.com). Ver README para como conectar o playground.
"""

from agno.os import AgentOS
from fastapi import FastAPI

from agent_service.agents.registry import all_agents
from agent_service.api.routes import router
from agent_service.config import get_settings
from agent_service.db import get_db
from agent_service.documents.collections import all_collections
from agent_service.observability.tracing import configure_tracing

configure_tracing()

settings = get_settings()

base_app = FastAPI(title=settings.app_name)
base_app.include_router(router)

agent_os = AgentOS(
    id=settings.app_name,
    name=settings.app_name,
    db=get_db(),
    agents=all_agents(),
    knowledge=all_collections(),
    base_app=base_app,
    tracing=True,
)

app = agent_os.get_app()


if __name__ == "__main__":
    agent_os.serve(app="agent_service.main:app", host=settings.app_host, port=settings.app_port, reload=True)
