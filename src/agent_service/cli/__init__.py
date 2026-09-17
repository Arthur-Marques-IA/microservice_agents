"""CLI `kuro`: opera o agent-service pelo terminal, via HTTP.

É só um cliente da API (`client.py`) — nunca importa `agent_service.main`,
stores ou o banco, então roda sem Postgres/Fernet, apontando pra qualquer
instância do serviço (`--url` / `KURO_API_URL`).

Duas audiências, uma superfície:
- IA/scripts: todo comando é dirigível só por argumentos, `--json` em tudo,
  código de saída reflete falha semântica (ex.: tool com `ok: false`).
- Dev: sem argumento obrigatório e com TTY, abre seletores (`kuro agents`)
  e `kuro` sozinho abre um shell com `/agents`, `/tools`, `/chat`...
"""
