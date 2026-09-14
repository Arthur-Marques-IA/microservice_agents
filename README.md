# agent-service

Microserviço de agentes de IA para ser embarcado em uma plataforma maior,
ao lado de outros módulos. Constrói sobre o [Agno](https://docs.agno.com) as
abstrações de modelo, memória, tools e agentes, expõe um contrato de API
estável para os demais módulos, e usa o [AgentOS](https://docs.agno.com/agent-os)
do próprio Agno para tracing e o playground de testes.

## Stack

- **Python 3.12 + Agno** — framework de agentes (agent loop, memória, tools, knowledge).
- **FastAPI** — API HTTP, síncrona e streaming (SSE).
- **PostgreSQL + pgvector** — memória comum (sessões/histórico), tracing e collections de documentos.
- **Redis Streams** — mensageria assíncrona entre módulos da plataforma.
- **Google Gemini** — provedor de modelo inicial, via abstração em `models/provider.py`.
- **LangSmith** — observabilidade (tracing de execuções de agente).
- **Mem0** — camada de memória semântica opcional (fase 2).

## Estrutura

```
src/agent_service/
  api/            # contrato estável de API (/chat, /chat/stream, /health)
  agents/         # tipos de agente (conversacional implementado; orquestrador/analista no roadmap)
  memory/         # abstração de memória (comum via Agno/Postgres; Mem0 como backend plugável)
  models/         # abstração de provedor de modelo (LLM)
  tools/          # registro de tools por tipo de agente
  documents/      # collections de documentos (pgvector) para RAG
  messaging/      # producer/consumer Redis Streams
  observability/  # tracing via LangSmith
  db.py           # instância compartilhada do Postgres (agno.db.postgres.PostgresDb)
  config.py       # settings (env vars)
  main.py         # FastAPI + AgentOS
tests/
```

## Rodando localmente

1. Suba a infra:

   ```bash
   docker compose up -d
   ```

   Postgres+pgvector fica em `localhost:55432` (55432 para não colidir com um Postgres nativo já rodando na 5432) e Redis em `localhost:6379`.

2. Copie `.env.example` para `.env` e preencha `GOOGLE_API_KEY` (e opcionalmente `LANGSMITH_API_KEY`/`LANGSMITH_TRACING_ENABLED=true`).

3. Instale as dependências e suba a API:

   ```bash
   uv sync
   uv run uvicorn agent_service.main:app --app-dir src --reload
   ```

4. Teste o agente conversacional:

   ```bash
   curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"user_id": "u1", "session_id": "s1", "message": "oi, tudo bem?"}'
   ```

   Streaming: `GET /chat/stream?agent_type=conversational&user_id=u1&session_id=s1&message=oi`.

5. **Playground**: com a API rodando, conecte o playground hospedado em
   [os.agno.com](https://os.agno.com) apontando para `http://localhost:8000` —
   o AgentOS já expõe as rotas que o playground consome (sessões, execução,
   streaming). Não há UI local própria no MVP.

6. **Docs da API própria** (`/health`, `/chat`, `/agent-types`, `/collections`): `http://localhost:8000/docs`.

## Collections de documentos (RAG)

Cada nome em `COLLECTION_NAMES` (`documents/collections.py`) vira uma
`Knowledge` própria (tabela pgvector dedicada) e é registrada no AgentOS, que
já expõe o pipeline de ingestão completo:

- `POST /knowledge/content` (multipart) — upload de arquivo, texto (`text_content`)
  ou URL (`url`), com `reader_id`/`chunker`/`chunk_size`/`chunk_overlap`
  opcionais. Processado de forma assíncrona; acompanhe o status em
  `GET /knowledge/content/{content_id}/status`.
- `POST /knowledge/search` — busca semântica na base.
- `GET /knowledge/content` — lista o conteúdo já ingerido.

Para ingestão simples de texto sem lidar com multipart, o contrato estável do
serviço também expõe:

```bash
curl -X POST http://localhost:8000/collections/general/documents \
  -H "Content-Type: application/json" \
  -d '{"text": "conteúdo a indexar", "name": "meu-documento"}'

curl "http://localhost:8000/collections/general/search?query=algo&limit=5"
```

Isso cobre a ingestão; o **agente analista** que vai consumir essas coleções
via tool de busca continua no roadmap (fase 2).

## Memória com Mem0

Por padrão o serviço usa a memória comum (`memory/common.py`, sobre Postgres,
gerenciada nativamente pelo Agno). Para trocar o agente conversacional para
usar o [Mem0](https://mem0.ai) como memória semântica:

1. Instale o extra: `uv sync --extra mem0`.
2. No `.env`: `MEM0_ENABLED=true` e `MEM0_API_KEY=<sua chave>`.

Com isso, `agents/conversational.py` passa `memory_backend="mem0"` para
`build_agent`, que liga `memory/mem0_hooks.py` como `pre_hooks`/`post_hooks`
do Agent: antes de responder, busca memórias relevantes no Mem0 e injeta em
`dependencies.mem0_memories`; depois de responder, grava a mensagem do
usuário no Mem0. A memória comum continua ativa em paralelo (histórico de
sessão), então os dois backends coexistem — não há troca completa, só adição
da camada semântica do Mem0.

## Testes

```bash
uv run pytest
```

## Escopo do MVP (implementado)

- Abstrações centrais: `BaseAgent` (`agents/base.py`), memória comum (`memory/common.py`),
  gerenciamento de modelo (`models/provider.py`), registro de tools (`tools/registry.py`).
- Agente **conversacional** ponta a ponta, usando Gemini, com histórico e memórias
  persistidos em Postgres.
- API REST síncrona (`POST /chat`) e streaming (`GET /chat/stream`).
- Observabilidade via LangSmith (`observability/tracing.py`) + tracing nativo do
  AgentOS (guardado no Postgres, visível pelo playground).
- Collections de documentos via pgvector, com pipeline de ingestão completo
  (`documents/collections.py` + rotas nativas do AgentOS em `/knowledge/*`,
  mais o atalho `/collections/{name}/documents` para texto simples).
- Memória semântica via Mem0, plugável por agente através de pre/post hooks
  (`memory/mem0_backend.py` + `memory/mem0_hooks.py`); o agente conversacional
  já usa esse backend quando `MEM0_ENABLED=true`.
- Esqueleto pronto para evoluir: mensageria via Redis Streams (`messaging/`).

## Roadmap (fase 2+)

- **Agente orquestrador**: roteia entre conversacional/analista, consumindo o
  stream de tarefas do Redis (`messaging/redis_streams.py::consume_tasks` já
  está pronto para virar a base de um worker).
- **Agente analista**: usa `documents/collections.py` (knowledge/RAG) via uma
  tool de busca — a base de conhecimento e a ingestão já existem, falta o
  agente que a consome.
- **Mem0 selecionável por sessão** (hoje é por agente/config global via
  `MEM0_ENABLED`): permitir escolher o backend de memória por request.
- **Múltiplos provedores de LLM**: adicionar branches em `models/provider.py`
  para OpenAI, Anthropic e modelos locais (Ollama/vLLM).
- **Gerenciamento de modelo mais rico**: fallback entre provedores, custo,
  rate limiting por tenant.
- **Autenticação/multi-tenancy** para uso dentro da plataforma (AgentOS já
  suporta `authorization=True`/`authorization_config`).
- **Métricas além do tracing**: exportar para OpenTelemetry/Grafana usando
  `agno.tracing.setup_tracing` como alternativa/complemento ao LangSmith.
- **CI/CD e deploy**: pipeline de testes + build de imagem, manifests de
  deploy (k8s ou equivalente da plataforma).
