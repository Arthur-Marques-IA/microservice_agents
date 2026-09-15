# agent-service

Microserviço de agentes de IA para ser embarcado em uma plataforma maior,
ao lado de outros módulos. Constrói sobre o [Agno](https://docs.agno.com) as
abstrações de modelo, memória, tools e agentes, expõe um contrato de API
estável para os demais módulos, usa o [AgentOS](https://docs.agno.com/agent-os)
do próprio Agno para tracing, e tem um frontend (Next.js) com chat/playground
e admin de collections. Todo o stack roda via Docker Compose.

## Stack

**Backend**
- **Python 3.12 + Agno** — framework de agentes (agent loop, memória, tools, knowledge).
- **FastAPI** — API HTTP, síncrona e streaming (SSE).
- **PostgreSQL + pgvector** — memória comum (sessões/histórico), tracing e collections de documentos.
- **Redis Streams** — mensageria assíncrona entre módulos da plataforma.
- **Google Gemini** — provedor de modelo inicial, via abstração em `models/provider.py`.
- **LangSmith** — observabilidade (tracing de execuções de agente).
- **Mem0** — camada de memória semântica opcional (fase 2).

**Frontend** (`frontend/`)
- **Next.js (App Router) + TypeScript** — chat/playground e admin de collections.
- **Tailwind CSS**, componentes no estilo shadcn/ui (escritos à mão em `components/ui/`, sem depender do CLI).
- Padrão **BFF**: o browser só fala com o Next.js. Os Route Handlers em `app/api/**`
  proxeiam para o `agent-service` usando a env var interna `AGENT_SERVICE_URL`
  (nunca exposta ao browser) — sem CORS, sem expor o backend publicamente.

**Infra**: Docker Compose orquestra Postgres+pgvector, Redis, `agent-service` e `frontend`.

## Estrutura

```
src/agent_service/
  api/            # contrato estável de API (/chat, /chat/stream, /health) + agents_routes.py (CRUD)
  agents/         # store.py (definições+versionamento no Postgres), registry.py (resolução dinâmica)
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
Dockerfile        # imagem do agent-service (uv, multi-stage)
frontend/
  src/app/          # chat, admin, e os Route Handlers do BFF (app/api/**)
  src/components/   # ui/ (primitivas), chat/, admin/
  src/lib/          # api.ts (proxy pro backend), sse.ts (parser SSE), hooks
  Dockerfile         # multi-stage, output standalone do Next.js
docker-compose.yml  # postgres, redis, agent-service, frontend
```

## Rodando localmente (Docker, recomendado)

1. Copie `.env.example` para `.env` e preencha `GOOGLE_API_KEY` (e opcionalmente
   `LANGSMITH_API_KEY`/`LANGSMITH_TRACING_ENABLED=true`). Esse `.env` é usado
   pelo `agent-service`; dentro do compose, `DATABASE_URL`/`REDIS_URL` são
   sobrescritas para os hostnames internos (`postgres`, `redis`) — os valores
   do `.env.example` para essas duas são só para rodar o backend fora do Docker.

2. Suba tudo:

   ```bash
   docker compose up -d --build
   ```

   | Serviço | URL no host | Observação |
   |---|---|---|
   | frontend | http://localhost:3000 | chat em `/chat`, admin em `/admin` |
   | agent-service | http://localhost:58000 | API própria; `/docs` pra explorar |
   | postgres | localhost:55432 | pgvector; porta não-default pra não colidir com um Postgres nativo |
   | redis | localhost:6379 | |

3. Teste o agente conversacional direto na API (sem passar pelo frontend):

   ```bash
   curl -X POST http://localhost:58000/chat \
     -H "Content-Type: application/json" \
     -d '{"user_id": "u1", "session_id": "s1", "message": "oi, tudo bem?"}'
   ```

   Streaming (SSE via POST — o corpo é o mesmo do `/chat`; não é `GET`
   porque `EventSource` do browser não manda corpo, então o cliente consome
   isso com `fetch` + leitura manual do stream, não com `EventSource`):

   ```bash
   curl -N -X POST http://localhost:58000/chat/stream \
     -H "Content-Type: application/json" \
     -d '{"user_id": "u1", "session_id": "s1", "message": "oi"}'
   ```

4. **Playground do AgentOS**: com o `agent-service` rodando, conecte o
   playground hospedado em [os.agno.com](https://os.agno.com) apontando para
   `http://localhost:58000` — o AgentOS já expõe as rotas que o playground
   consome (sessões, execução, streaming, tracing).

5. **Docs da API própria** (`/health`, `/chat`, `/agents`, `/tools`, `/collections`): `http://localhost:58000/docs`.

## Rodando sem Docker (dev do backend isolado)

```bash
uv sync
uv run uvicorn agent_service.main:app --app-dir src --reload
```

Usa o `DATABASE_URL`/`REDIS_URL` do `.env.example` (localhost, portas
publicadas pelo compose) — então ainda precisa de `docker compose up -d
postgres redis` rodando.

## Agentes: criação dinâmica e versionamento de prompt

Agentes não são mais hardcoded em Python — são linhas em `agent_definitions`
(Postgres), criadas/editadas via `/agents` (API) ou pela tela `/agents` do
frontend, e resolvidas em runtime sem restart do processo. O agente
`conversational` original é só a primeira linha, semeada automaticamente no
startup (`agents/seed.py`) se ainda não existir.

```bash
# criar
curl -X POST http://localhost:58000/agents -H "Content-Type: application/json" -d '{
  "agent_type": "suporte",
  "name": "Agente de Suporte",
  "instructions": ["Você é um agente de suporte técnico.", "Responda de forma objetiva."],
  "memory_backend": "common"
}'

# usar imediatamente, sem restart
curl -X POST http://localhost:58000/chat -H "Content-Type: application/json" \
  -d '{"agent_type": "suporte", "user_id": "u1", "session_id": "s1", "message": "meu wifi caiu"}'

# editar o prompt (cria uma nova versão automaticamente)
curl -X PUT http://localhost:58000/agents/suporte -H "Content-Type: application/json" \
  -d '{"instructions": ["Nova versão do prompt."]}'

# ver o histórico de versões (read-only, sem endpoint de rollback)
curl http://localhost:58000/agents/suporte/versions
```

Cada edição de `instructions` grava uma linha nova em `agent_prompt_versions`
e incrementa `prompt_version` — é auditoria/histórico, não um sistema de
rollback (reverter = editar de novo copiando o texto de uma versão antiga).
`memory_backend` (`"common"` ou `"mem0"`) e `model_provider`/`model_id`
também são campos por-agente agora, em vez da antiga env var global
`MEM0_ENABLED` (que continua existindo só como guarda de configuração do
Mem0 — ver seção abaixo).

`GET /tools` lista as tools disponíveis para o campo `tools` (nomes
resolvidos via `tools/registry.py::resolve_tools`, nunca código arbitrário
vindo da API).

**Parâmetros opcionais no chat (`dependencies`)**: `ChatRequest` aceita um
campo livre `dependencies` (ex: `{"cpf": "...", "nome": "..."}`) — vira
contexto estruturado injetado no prompt via `add_dependencies_to_context` do
Agno. Ver `/docs` no frontend para exemplos completos com cURL copiável.

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
curl -X POST http://localhost:58000/collections/general/documents \
  -H "Content-Type: application/json" \
  -d '{"text": "conteúdo a indexar", "name": "meu-documento"}'

curl "http://localhost:58000/collections/general/search?query=algo&limit=5"
```

Isso cobre a ingestão; o **agente analista** que vai consumir essas coleções
via tool de busca continua no roadmap (fase 2). O painel `/admin` do frontend
usa esses mesmos endpoints (+ upload de arquivo via `/knowledge/content`) e
faz polling de status até a ingestão terminar — a resposta do `POST` só
confirma que o backend aceitou o conteúdo, não que o embedding já rodou.

## Memória com Mem0

Por padrão todo agente usa a memória comum (`memory/common.py`, sobre
Postgres, gerenciada nativamente pelo Agno — é a memória "autogerenciada" do
Agno, o default do framework). Para um agente específico usar o
[Mem0](https://mem0.ai) como memória semântica:

1. Instale o extra: `uv sync --extra mem0`.
2. No `.env`: `MEM0_ENABLED=true` e `MEM0_API_KEY=<sua chave>`.
3. Crie ou edite o agente com `"memory_backend": "mem0"` (via `POST/PUT
   /agents`, ou pelo formulário em `/agents` no frontend).

Com isso, `agents/base.py::build_agent` liga `memory/mem0_hooks.py` como
`pre_hooks`/`post_hooks` do Agent: antes de responder, busca memórias
relevantes no Mem0 e injeta em `dependencies.mem0_memories`; depois de
responder, grava a mensagem do usuário no Mem0. A memória comum continua
ativa em paralelo (histórico de sessão), então os dois backends coexistem —
não há troca completa, só adição da camada semântica do Mem0.

## Frontend

Quatro áreas, sem autenticação nesse MVP (`user_id` **e** `session_id`
gerados e guardados no `localStorage` do browser — os dois persistem entre
reloads, senão o agente "esquece tudo" a cada F5):

- **`/chat`** — playground de conversa. Seletor de agente mostra o `name`
  de cada um (lista rica vem de `GET /agents`), botão "Nova sessão" gera um
  `session_id` novo, resposta renderiza em streaming, e ao final aparece um
  badge com o total de tokens consumidos (`event: usage` do SSE — é o total
  ao terminar a resposta, não incremental token a token, porque é o que o
  Agno expõe).
- **`/agents`** — criar/editar agentes (nome, prompt, modelo, memória,
  tools) por formulário, sem tocar em código. Cada agente tem uma aba de
  histórico de prompt (read-only — sem botão de reverter, ver seção acima).
- **`/admin`** — uma seção por collection configurada (`COLLECTION_NAMES` no
  backend): ingestão de texto, upload de arquivo, e busca semântica. Todo
  upload mostra um badge de status (`Processando... → Concluído/Parcial/Falhou`)
  porque a ingestão é assíncrona no backend.
- **`/docs`** — exemplo de cURL copiável para `/chat` e `/chat/stream`,
  parâmetros obrigatórios/opcionais — pensado pra outro time da plataforma
  copiar e integrar sem precisar ler o código.

Nenhuma página fala com o `agent-service` diretamente — tudo passa pelos
Route Handlers em `frontend/src/app/api/**`, que fazem proxy usando
`AGENT_SERVICE_URL` (só server-side, sem prefixo `NEXT_PUBLIC_`). O streaming
do chat é `fetch` + leitura manual do `ReadableStream` (`lib/sse.ts`), não
`EventSource`, porque o endpoint é `POST`. Componentes de UI novos
(`Select`, `Dialog`, `Tabs`, `CodeBlock`) seguem o mesmo padrão hand-written
dos já existentes — sem `@radix-ui`/`class-variance-authority`.

Dev sem Docker:

```bash
cd frontend
npm install
AGENT_SERVICE_URL=http://localhost:58000 npm run dev
```

## Testes

```bash
uv run pytest
```

## Escopo do MVP (implementado)

- Abstrações centrais: `BaseAgent` (`agents/base.py`), memória comum (`memory/common.py`),
  gerenciamento de modelo (`models/provider.py`), registro de tools (`tools/registry.py`).
- **Agentes dinâmicos**: definições + versionamento de prompt em Postgres
  (`agents/store.py`), resolvidos em runtime (`agents/registry.py`) sem
  restart — CRUD completo via `/agents` (API) e pela tela `/agents`
  (frontend). O agente `conversational` é só a primeira linha semeada.
- API REST síncrona (`POST /chat`, com `dependencies` opcionais) e streaming
  (`POST /chat/stream`, com tracing e `event: usage` de tokens ao final).
- Observabilidade via LangSmith (`observability/tracing.py`, cobrindo tanto
  `/chat` quanto `/chat/stream`) + tracing nativo do AgentOS (guardado no
  Postgres, visível pelo playground).
- Collections de documentos via pgvector, com pipeline de ingestão completo
  (`documents/collections.py` + rotas nativas do AgentOS em `/knowledge/*`,
  mais o atalho `/collections/{name}/documents` para texto simples).
- Memória semântica via Mem0, plugável por agente através de pre/post hooks
  (`memory/mem0_backend.py` + `memory/mem0_hooks.py`) — `memory_backend` é um
  campo por-agente (`"common"` ou `"mem0"`), configurável via `/agents`.
- Esqueleto pronto para evoluir: mensageria via Redis Streams (`messaging/`).
- **Todo o stack containerizado** (`Dockerfile` do backend, `frontend/Dockerfile`,
  `docker-compose.yml` orquestrando os quatro serviços) — `docker compose up
  -d --build` sobe tudo.
- **Frontend Next.js** (`frontend/`) com chat/playground (streaming real,
  badge de tokens), gerenciamento de agentes (`/agents`), admin de
  collections e página de integração (`/docs`), como BFF na frente do
  `agent-service`.

## Roadmap (fase 2+)

- **Fallback de modelo**: o Agno já suporta `fallback_models`/`fallback_config`
  nativamente (`agno.models.fallback.FallbackConfig`) — deliberadamente não
  ligado ainda (hoje só há Gemini configurado). Entra quando houver um
  segundo modelo/provedor real para compor a cadeia.
- **Agente orquestrador**: roteia entre conversacional/analista, consumindo o
  stream de tarefas do Redis (`messaging/redis_streams.py::consume_tasks` já
  está pronto para virar a base de um worker).
- **Agente analista**: usa `documents/collections.py` (knowledge/RAG) via uma
  tool de busca — a base de conhecimento e a ingestão já existem, falta o
  agente que a consome.
- **Rollback de versão de prompt**: hoje o histórico em
  `agent_prompt_versions` é só leitura/auditoria — reverter é editar de novo
  copiando o texto antigo. Um endpoint `POST /agents/{type}/versions/{v}/activate`
  fecharia isso.
- **Reidratar histórico de mensagens na tela**: o fix do bug de memória só
  persistiu `session_id`/`user_id` no `localStorage` — o agente lembra o
  contexto entre reloads, mas as bolhas de chat na UI começam vazias até a
  próxima mensagem. Precisa de um endpoint pra buscar o histórico da sessão.
- **Upload de arquivo por collection**: `POST /knowledge/content` hoje resolve
  a collection automaticamente porque só existe uma (`general`). Com mais de
  uma em `COLLECTION_NAMES`, o proxy em `frontend/src/app/api/knowledge/content/route.ts`
  precisa passar `knowledge_id` (e o admin, deixar escolher a collection no
  upload) — a ingestão de texto já suporta isso via `/collections/{name}/documents`.
- **Auth no frontend**: hoje sem login, `user_id` só vive no `localStorage`
  do browser. Entra quando a plataforma tiver um sistema de auth definido.
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
