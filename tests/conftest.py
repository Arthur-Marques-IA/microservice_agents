import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

os.environ.setdefault("GOOGLE_API_KEY", "test-key")
# Arquivo, não `:memory:`: o SQLite em memória é um banco por thread, e as rotas
# fazem o I/O do banco numa thread do pool (`run_in_threadpool`).
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(tempfile.mkdtemp()) / 'agent_service.db'}")
os.environ.setdefault("CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())

from agent_service.agents.seed import seed_default_agents  # noqa: E402
from agent_service.migrations import upgrade_database  # noqa: E402
from agent_service.tools.seed import seed_default_tools  # noqa: E402
from agent_service.documents.store import seed_default_collection  # noqa: E402

upgrade_database()
seed_default_collection()
seed_default_tools()
seed_default_agents()

import socket  # noqa: E402

import pytest  # noqa: E402

from agent_service.observability import run_store  # noqa: E402
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


@pytest.fixture(autouse=True)
def gravacao_sincrona(monkeypatch):
    """O trace store local grava numa thread sem esperar, para não atrasar a
    resposta. Nos testes grava na hora, para o teste poder ler logo em seguida."""
    monkeypatch.setattr(run_store, "_submit", lambda fn: fn())
