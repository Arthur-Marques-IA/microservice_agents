import os

from cryptography.fernet import Fernet

os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())

from agent_service.agents.seed import seed_default_agents  # noqa: E402
from agent_service.agents.store import init_store  # noqa: E402
from agent_service.models.store import init_store as init_model_provider_store  # noqa: E402
from agent_service.tools.seed import seed_default_tools  # noqa: E402
from agent_service.documents.store import init_store as init_collection_store  # noqa: E402
from agent_service.documents.store import seed_default_collection  # noqa: E402
from agent_service.tools.store import init_store as init_tool_store  # noqa: E402

init_store()
init_tool_store()
init_model_provider_store()
init_collection_store()
seed_default_collection()
seed_default_tools()
seed_default_agents()

import socket  # noqa: E402

import pytest  # noqa: E402

from agent_service.tools import egress  # noqa: E402

_IP_PUBLICO = "93.184.216.34"
DNS_DO_SISTEMA = socket.getaddrinfo
"""Guardado antes de qualquer teste trocar o resolvedor — ver `resolvedor_real`."""


@pytest.fixture
def resolvedor_real(monkeypatch):
    """Desfaz o `dns_deterministico` para o teste que precisa do resolvedor do SO.

    Sem isto nenhum teste exercitaria `getaddrinfo` de verdade, e um erro nos
    argumentos ou no índice da tupla que ele devolve passaria batido em toda a
    suíte para só aparecer na primeira chamada real."""
    monkeypatch.setattr(egress.socket, "getaddrinfo", DNS_DO_SISTEMA)


@pytest.fixture(autouse=True)
def dns_deterministico(monkeypatch):
    """Nenhum teste consulta DNS de verdade.

    O controle de egress (`tools/egress.py`) resolve o host antes de deixar uma
    tool sair para a rede. Sem isto, os testes de tool dependeriam de rede e de
    hosts reais — e `exemplo.test` nem resolve. Todo host passa a ser público;
    o teste que quer ver o bloqueio acontecendo substitui isto por conta dele.
    """
    def resolve(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (_IP_PUBLICO, port))]

    monkeypatch.setattr(egress.socket, "getaddrinfo", resolve)
