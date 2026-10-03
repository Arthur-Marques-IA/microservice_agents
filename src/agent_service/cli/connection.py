"""De onde vem a conexão com o serviço quando não há flags de linha de comando.

A CLI resolve URL, chave e certificado pelas opções do `typer` (que leem as mesmas
variáveis); o servidor MCP e a TUI não têm essas flags e chamam `client_from_env`.
Os nomes são os mesmos nos três, então quem já configurou a CLI não configura de novo.
"""

import os

from agent_service.cli.client import Client

# 127.0.0.1, não localhost: no Windows `localhost` tenta IPv6 (::1) primeiro e o
# port-forward do Docker Desktop nesse caminho derruba conexões de forma intermitente.
DEFAULT_URL = "http://127.0.0.1:58000"

_TRUE = ("1", "true", "yes", "sim")


def client_from_env(timeout: float = 120.0) -> Client:
    """`KURO_API_URL` (ou `AGENT_SERVICE_URL`), `KURO_API_KEY`, `KURO_CA_BUNDLE` e
    `KURO_INSECURE=1` (só para teste local com certificado autoassinado)."""
    url = os.environ.get("KURO_API_URL") or os.environ.get("AGENT_SERVICE_URL") or DEFAULT_URL
    insecure = os.environ.get("KURO_INSECURE", "").strip().lower() in _TRUE
    verify: bool | str = False if insecure else (os.environ.get("KURO_CA_BUNDLE") or True)
    return Client(url, timeout=timeout, api_key=os.environ.get("KURO_API_KEY") or None, verify=verify)
