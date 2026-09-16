# agent-service

Microserviço de agentes de IA para ser embarcado em uma plataforma maior,
ao lado de outros módulos. Constrói sobre o [Agno](https://docs.agno.com) as
abstrações de modelo, memória, tools e agentes, expõe um contrato de API
estável para os demais módulos, usa o [AgentOS](https://docs.agno.com/agent-os)
do próprio Agno para sessões e ingestão de conhecimento, manda a
observabilidade para um [Langfuse](https://langfuse.com) self-hosted, e tem um
console web (Next.js) que integra playground, gestão de agentes e base de
conhecimento. Todo o stack roda via Docker Compose.

## Stack

**Backend**
- **Python 3.12 + Agno** — framework de agentes (agent loop, memória, tools, knowledge).
- **FastAPI** — API HTTP, síncrona e streaming (SSE).
- **PostgreSQL + pgvector** — memória comum (sessões/histórico) e collections de documentos.
- **Redis Streams** — mensageria assíncrona entre módulos da plataforma.
- **Google Gemini** — provedor de modelo inicial, via abstração em `models/provider.py`.
- **Langfuse** (self-hosted) — observabilidade: traces das execuções via OpenTelemetry/OpenInference, custo, sessões e feedback.
- **Mem0** — camada de memória semântica opcional (fase 2).

**Frontend** (`frontend/`)
- **Next.js (App Router) + TypeScript** — console único: playground, agentes e base de conhecimento.
- **Tailwind CSS**, componentes no estilo shadcn/ui (escritos à mão em `components/ui/`, sem depender do CLI).
- Padrão **BFF**: o browser só fala com o Next.js. Os Route Handlers em `app/api/**`
  proxeiam para o `agent-service` usando a env var interna `AGENT_SERVICE_URL`
  (nunca exposta ao browser) — sem CORS, sem expor o backend publicamente.

**Infra**: Docker Compose orquestra Postgres+pgvector, Redis, `agent-service`,
`frontend` e o stack do Langfuse (web, worker e os bancos dele).

## Estrutura

```
src/agent_service/
  api/            # contrato estável de API (/chat, /chat/stream, /health) + agents_routes.py/tools_routes.py (CRUD)
  agents/         # store.py (definições+versionamento no Postgres), registry.py (resolução dinâmica)
  memory/         # abstração de memória (comum via Agno/Postgres; Mem0 como backend plugável)
  models/         # abstração de provedor de modelo (LLM)
  tools/          # store.py (CRUD), catalog.py (builtins do Agno), api_tool.py, python_tool.py, registry.py (resolução)
  documents/      # collections de documentos (pgvector) para RAG
  messaging/      # producer/consumer Redis Streams
  observability/  # tracing.py: Langfuse + instrumentação do Agno; trace_store.py: leitura de runs/traces
  db.py           # instância compartilhada do Postgres (agno.db.postgres.PostgresDb)
  config.py       # settings (env vars)
  main.py         # FastAPI + AgentOS
tests/
Dockerfile        # imagem do agent-service (uv, multi-stage)
frontend/
  src/app/(workspace)/ # console: chat/, agents/, tools/, knowledge/, observability/ sob um layout com sidebar
  src/app/api/         # Route Handlers do BFF (proxy pro agent-service)
  src/components/      # ui/ (primitivas), workspace/ (shell, sidebar, paleta), chat/, agents/, tools/, knowledge/, integration/
  src/lib/             # api.ts (proxy), sse.ts (parser SSE), use-chat.ts, sessions.ts, hooks
  Dockerfile         # multi-stage, output standalone do Next.js
docker-compose.yml  # postgres, redis, agent-service, frontend + stack do Langfuse
```

## Rodando localmente (Docker, recomendado)

1. Copie `.env.example` para `.env` e preencha `GOOGLE_API_KEY`. Esse `.env` é
   usado pelo `agent-service`; dentro do compose, `DATABASE_URL`/`REDIS_URL` e
   as variáveis do Langfuse são sobrescritas para os hostnames internos
   (`postgres`, `redis`, `langfuse-web`) — os valores do `.env.example` para
   elas são só para rodar o backend fora do Docker. As chaves do Langfuse já
   vêm com defaults de dev (ver **Observabilidade** abaixo).

2. Suba tudo:

   ```bash
   docker compose up -d --build
   ```

   | Serviço | URL no host | Observação |
   |---|---|---|
   | frontend | http://localhost:3000 | console: `/chat`, `/agents`, `/knowledge`, `/observability` |
   | agent-service | http://localhost:58000 | API própria; `/docs` pra explorar |
   | postgres | localhost:55432 | pgvector; porta não-default pra não colidir com um Postgres nativo |
   | redis | localhost:6379 | |

   O Langfuse (`langfuse-web`, `langfuse-worker` e os bancos dele) roda só na
   rede interna do compose, sem porta publicada — ninguém loga nele. Ele é o
   armazenamento dos traces; quem olha as execuções é o console, em
   `/observability` (ver a seção **Observabilidade** abaixo). O primeiro boot
   demora (migrações do ClickHouse) e o stack pede memória — o projeto
   recomenda ~4 CPUs / 16 GB. Ele não é pré-requisito do `agent-service`: com
   o Langfuse fora do ar os runs continuam normais, só não são rastreados.

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
   consome (sessões, execução, streaming).

5. **Docs da API própria** (`/health`, `/chat`, `/agents`, `/tools`, `/collections`): `http://localhost:58000/docs`.

## Rodando sem Docker (dev do backend isolado)

```bash
uv sync
uv run uvicorn agent_service.main:app --app-dir src --reload
```

Usa o `DATABASE_URL`/`REDIS_URL` do `.env.example` (localhost, portas
publicadas pelo compose) — então ainda precisa de `docker compose up -d
postgres redis` rodando (mais `docker compose up -d langfuse-web`, que puxa
os bancos dele, se quiser tracing; `LANGFUSE_BASE_URL` do `.env.example`
já aponta para `http://localhost:3100`, publicada só em `127.0.0.1`).

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

`GET /tools` lista as tools disponíveis para o campo `tools` (só os nomes são
salvos na definição do agente — a tool em si é resolvida em runtime, ver
**Tools dos agentes** abaixo).

**Parâmetros opcionais no chat (`dependencies`)**: `ChatRequest` aceita um
campo livre `dependencies` (ex: `{"cpf": "...", "nome": "..."}`) — vira
contexto estruturado injetado no prompt via `add_dependencies_to_context` do
Agno. Ver a aba **Integração** de cada agente no console para exemplos
completos (cURL, JavaScript e Python).

## Tools dos agentes

Tools são criadas pela API ou pela tela `/tools` do console — nunca editando
`tools/registry.py`, que só resolve o nome salvo em `AgentDefinition.tools`
pro objeto real do Agno em runtime (`agents/registry.py` chama isso a cada
`/chat`, com cache invalidado por `updated_at`, igual ao agente em si). Uma
tabela só (`tool_definitions`), três formatos (`kind`):

| `kind` | O que é | Onde mora a config |
|---|---|---|
| `builtin` | Uma toolkit padrão do Agno, do catálogo curado em `tools/catalog.py` (busca na web, calculadora, Hacker News, e-mail, arquivos...) | `{"builtin_id": "...", "params": {...}}` |
| `api` | Chama uma API HTTP existente, descrita em JSON — sem escrever código | método, URL (com `{param}` de path), parâmetros que o modelo preenche, autenticação |
| `python` | Uma função Python enviada por você, `exec`ada num namespace restrito | `{"code": "def handler(...): ...", "entrypoint": "handler"}` |

```bash
# catálogo de builtins disponíveis (id, params aceitos)
curl http://localhost:58000/tools/catalog

# criar uma tool builtin
curl -X POST http://localhost:58000/tools -H "Content-Type: application/json" -d '{
  "tool_name": "web_search", "kind": "builtin", "label": "Busca na web",
  "config": {"builtin_id": "web_search", "params": {"max_results": 5}}
}'

# criar uma tool de API — sem código, só descrição
curl -X POST http://localhost:58000/tools -H "Content-Type: application/json" -d '{
  "tool_name": "cep", "kind": "api", "label": "Consulta de CEP",
  "config": {
    "method": "GET", "url": "https://viacep.com.br/ws/{cep}/json/",
    "parameters": [{"name": "cep", "type": "string", "location": "path", "required": true}]
  }
}'

# testar uma tool sem montar um agente em volta dela
curl -X POST http://localhost:58000/tools/cep/invoke -H "Content-Type: application/json" \
  -d '{"arguments": {"cep": "01310-100"}}'

# usar no agente, como sempre
curl -X PUT http://localhost:58000/agents/conversational -H "Content-Type: application/json" \
  -d '{"tools": ["web_search", "cep"]}'
```

`GET/PUT /tools/{name}` mascaram segredos (token de auth, senha de app de
e-mail) na resposta — editar sem mexer no campo mascarado preserva o valor
real salvo. Excluir é bloqueado se a tool for semeada pelo sistema (`is_seed`)
ou estiver em uso por algum agente (a resposta diz qual). `POST
/tools/{name}/invoke` roda a tool uma vez fora de um agente — pra `kind:
"builtin"`, que expõe várias funções por toolkit, é obrigatório informar
`function_name` (a lista vem em `GET /tools/{name}.functions`).

**Tools Python são desligadas por padrão** (`CUSTOM_PYTHON_TOOLS_ENABLED=false`).
Dá pra criar e editar mesmo desligado — só não roda (nem num agente, nem em
`/invoke`) até ligar a env var. A validação (`tools/python_tool.py`) recusa
código com `import` fora de uma lista liberada (math, json, re, datetime,
statistics, httpx, random...) e qualquer nome/atributo perigoso (`os`,
`subprocess`, `eval`, `__globals__`, `__subclasses__`...), mais `builtins`
restritos na execução. **Isso não é uma sandbox forte** — é uma barreira
contra erro e abuso acidental, não contra um autor mal-intencionado
determinado (exigiria isolar por processo/container, fora do escopo deste
serviço). Só ligue se todo mundo com acesso à API/console já for confiável —
hoje o serviço não tem autenticação (ver **Roadmap**).

`web_search` (builtin) precisa do extra `tools`: `uv sync --extra tools`
(instala `ddgs`). As demais builtins do catálogo já funcionam sem instalar
nada. O seed cria três tools de exemplo prontas pra usar (`calculator`,
`hackernews`, `cat_fact` — uma tool de API pública, sem segredo nenhum).

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
via tool de busca continua no roadmap (fase 2). A tela `/knowledge` do console
usa esses mesmos endpoints (+ upload de arquivo/URL e listagem via
`/knowledge/content`) e atualiza a lista sozinha enquanto houver item
processando — a resposta do `POST` só confirma que o backend aceitou o
conteúdo, não que o embedding já rodou.

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

## Observabilidade (Langfuse)

Toda execução de agente vira um trace no [Langfuse](https://langfuse.com), que
roda self-hosted no próprio compose — como armazenamento interno, não como
uma tela do produto: ninguém precisa abrir ou logar na UI dele, o console tem
sua própria página (`/observability`, ver a seção **Frontend**) que lê os
mesmos dados pela API. `observability/tracing.py` cria o cliente do Langfuse e liga o
`AgnoInstrumentor` (OpenInference) ao TracerProvider dele — daí cada trace
mostra:

- a observação raiz do endpoint (`chat` ou `chat.stream`), com a mensagem, o
  `dependencies` enviado e a resposta final;
- o run do agente, **cada chamada ao modelo** (prompt completo, resposta,
  tokens, latência — o custo o Langfuse calcula pela tabela de preços dele) e
  **cada tool call** (argumentos, resultado, duração);
- `user_id` e `session_id` (a aba *Sessions* junta a conversa inteira),
  `trace_name` = slug do agente, tags e `version = prompt-v{N}`, o que permite
  comparar versões de prompt no dashboard.

O `run_id` é gerado pelo serviço **antes** do run e o trace usa um id derivado
dele (`Langfuse.create_trace_id(seed=run_id)`), então qualquer resposta —
inclusive as reidratadas do histórico — aponta para o próprio trace. O envio é
em lote e em background: não atrasa nem derruba a resposta. Sem
`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` (ou com `LANGFUSE_ENABLED=false`)
o tracing vira no-op e o serviço segue igual.

**Chaves e acesso administrativo**: no primeiro boot o `langfuse-web`
provisiona (headless init) a organização/projeto `agent-service`, as chaves de
API que o serviço usa e o usuário `LANGFUSE_INIT_USER_EMAIL`/
`LANGFUSE_INIT_USER_PASSWORD` — tudo com defaults de dev no
`docker-compose.yml`. Esse login só importa se você mesmo (infra/admin)
precisar abrir a UI do Langfuse para algo que a nossa API ainda não cobre (um
avaliador automático, a tabela de preços de um modelo novo): a porta
`langfuse-web` é publicada só em `127.0.0.1:3100`, então em `http://localhost:3100`
na própria máquina onde o compose roda. Troque os valores marcados `CHANGEME`
(salt, `ENCRYPTION_KEY`, senhas de Postgres/ClickHouse/Redis/MinIO, chaves do
projeto, login) em qualquer ambiente que não seja a sua máquina. Para usar o
**Langfuse Cloud** no lugar do self-hosted, apague os serviços `langfuse-*` do
compose e aponte `LANGFUSE_BASE_URL=https://cloud.langfuse.com` com as chaves
do seu projeto.

**Feedback e scores**: outros módulos (e o console) avaliam uma resposta pelo
`run_id`, que vira um score no trace:

```bash
curl -X POST http://localhost:58000/observability/scores \
  -H "Content-Type: application/json" \
  -d '{"run_id": "<run_id>", "name": "feedback", "value": 1, "user_id": "u1"}'
```

`feedback` é booleano (1 👍 / 0 👎; o último voto de cada usuário substitui o
anterior); qualquer outro nome é numérico, para notas de avaliação automática.
`GET /observability/config` diz se o tracing está ligado. O `run_id` vem em
`ChatResponse.run_id` e no primeiro evento do streaming (`event: run`).

**Leitura dos traces sem abrir o Langfuse**: `observability/trace_store.py` lê
a API pública dele (as chaves ficam só no servidor) e devolve os dados num
contrato próprio — o console usa essas rotas (é o que a página
`/observability` mostra) e outros módulos também podem usar:

```bash
# execuções de todos os agentes (mais recentes primeiro), com latência, tokens, custo e 👍/👎
curl "http://localhost:58000/observability/runs?limit=20&status=error"
# de um agente só: &agent_type=conversational (ou GET /observability/agents/conversational/runs)
# próxima página: &cursor=<next_cursor>

# trace completo de um run: resumo, spans (árvore via parent_id) e scores
curl http://localhost:58000/observability/runs/<run_id>/trace
```

Os filtros aceitos são `agent_type`, `prompt_version`, `status`
(`success`/`error`/`interrupted`), `user_id`, `session_id`, `since`/`until`
(ISO 8601), `limit` (≤ 100) e `cursor`. A ingestão do Langfuse é assíncrona: um
run recém-terminado leva alguns segundos para aparecer, e até lá o `/trace`
responde 404. `TraceStore` é uma interface — trocar o Langfuse por outro
backend não muda o contrato.

Limitações conhecidas do Langfuse v4: a API de scores não filtra vários traces
de uma vez, então a listagem cruza o feedback do período no próprio serviço —
com avaliações demais, `feedback_up`/`feedback_down` voltam `null` (o `/trace`
sempre traz a contagem exata). E a API de métricas não cruza scores com
atributos do trace, então "taxa de 👍 por versão do prompt" vai exigir um
índice próprio.

## Frontend

Um console único, em vez de abas isoladas. Um layout compartilhado
(`app/(workspace)/layout.tsx`) busca no servidor o que todas as áreas usam
(agentes, tools, collections) e envolve tudo numa sidebar persistente:

- **Sidebar** — nova conversa, busca/paleta de comandos (`Ctrl/⌘+K`),
  navegação entre as áreas (inclusive **Observabilidade**, quando o Langfuse
  está ligado), **histórico de conversas** agrupado por data
  (renomear/excluir), status da API e tema claro/escuro/sistema. Recolhível
  (`Ctrl/⌘+B`); vira gaveta no mobile.
- **Playground (`/chat`, `/chat/[sessionId]`)** — conversa em streaming com
  qualquer agente. Cada conversa tem URL própria e o histórico é
  **reidratado** a partir dos runs do AgentOS (`GET /sessions/{id}/runs`):
  recarregar a página não perde mais as mensagens. O painel de detalhes
  mostra agente, `session_id`/`user_id` e tokens (total ao fim de cada
  resposta, via `event: usage`), edita o **contexto (`dependencies`)**
  enviado a cada mensagem, abre o agente num painel lateral para ajustar o
  prompt sem sair da conversa e gera o **código de integração** equivalente.
  Cada resposta tem 👍/👎 (vira o score `feedback` do trace no Langfuse) e um
  link **Trace**, que abre a execução no próprio console.
- **Trace de uma execução (`/runs/[runId]`)** — latência, tokens, custo e
  feedback; a cascata de spans (agente → chamadas ao modelo → tools) e, para o
  span selecionado, entrada/saída (mensagens do prompt formatadas), modelo,
  tokens e metadados; mais as avaliações registradas. Enquanto o run ainda
  está sendo indexado, a página tenta de novo sozinha.
- **Observabilidade (`/observability`)** — execuções de todos os agentes numa
  lista só, filtrável por agente e status (a aba *Execuções* de cada agente é
  a mesma tela, já filtrada). O inspector do chat linka pra cá filtrado por
  sessão ou usuário. É a substituta da UI do Langfuse dentro do console —
  ninguém precisa abrir nem logar nele.
- **Agentes (`/agents`, `/agents/new`, `/agents/[slug]`)** — lista com busca;
  a página do agente reúne *Configuração* (formulário com detecção de
  alterações — só os campos alterados vão no `PUT`, então editar o nome não
  cria versão de prompt), *Versões* (histórico com diff contra a atual e
  "restaurar no editor", que salva como nova versão), *Execuções* (todas as
  chamadas ao agente, de qualquer origem, filtráveis por versão do prompt e
  status, cada uma abrindo o trace), *Conversas* com o
  agente e *Integração* (cURL/JavaScript/Python + referência do contrato
  `/chat` e `/chat/stream`, no lugar da antiga página `/docs`). O multi-select
  de tools mostra o tipo (builtin/API/Python) de cada uma, com um link para a
  tela de gerenciamento.
- **Tools (`/tools`)** — lista com busca, criação e edição de tools dos três
  tipos (formulário próprio por tipo: escolher a toolkit e seus parâmetros
  para builtin; método, URL, parâmetros e autenticação para API; editor de
  código e função de entrada para Python), um botão **Testar** que roda a
  tool uma vez fora de um agente (`POST /tools/{name}/invoke`) e exclusão
  (bloqueada se a tool estiver em uso). Campos secretos (token de auth, senha
  de app de e-mail) vêm mascarados do backend e só mudam se você de fato
  editá-los.
- **Base de conhecimento (`/knowledge`)** — tabela dos documentos ingeridos
  (`GET /knowledge/content`) com status e mensagem de erro, atualização
  automática enquanto algo processa, exclusão, adição por texto, arquivo
  (arrastar e soltar) ou URL, e um painel para testar a busca semântica.
  Substitui o antigo `/admin`.

As rotas antigas redirecionam (`/admin` → `/knowledge`, `/docs` → `/agents`).
Sem autenticação no MVP: o `user_id` é gerado e guardado no `localStorage`
do browser, e a sidebar lista só as conversas desse `user_id`.

Nenhuma página fala com o `agent-service` diretamente — tudo passa pelos
Route Handlers em `frontend/src/app/api/**` (inclusive os de sessões e
conteúdo do AgentOS), que fazem proxy usando `AGENT_SERVICE_URL` (só
server-side, sem prefixo `NEXT_PUBLIC_`); `AGENT_SERVICE_PUBLIC_URL` serve
apenas para montar os exemplos de integração. O streaming do chat é `fetch`
+ leitura manual do `ReadableStream` (`lib/sse.ts`), não `EventSource`,
porque o endpoint é `POST`. As respostas renderizam markdown
(`react-markdown` + `remark-gfm`, sem HTML bruto). Os componentes de UI
(`components/ui/`: `Dialog`/sheet, `DropdownMenu`, `Tabs`, `Toast`,
`Confirm`…) seguem escritos à mão, sem `@radix-ui`/`class-variance-authority`.

Dev sem Docker:

```bash
cd frontend
npm install
# AGENT_SERVICE_PUBLIC_URL é opcional: só muda a URL exibida nos exemplos de integração.
AGENT_SERVICE_URL=http://localhost:58000 AGENT_SERVICE_PUBLIC_URL=http://localhost:58000 npm run dev
```

## Testes

```bash
uv run pytest
```

## Escopo do MVP (implementado)

- Abstrações centrais: `BaseAgent` (`agents/base.py`), memória comum (`memory/common.py`),
  gerenciamento de modelo (`models/provider.py`).
- **Agentes dinâmicos**: definições + versionamento de prompt em Postgres
  (`agents/store.py`), resolvidos em runtime (`agents/registry.py`) sem
  restart — CRUD completo via `/agents` (API) e pela tela `/agents`
  (frontend). O agente `conversational` é só a primeira linha semeada.
- **Tools construídas via API/console, sem código** (`tools/store.py` +
  `api/tools_routes.py`): builtins do Agno (`tools/catalog.py`), chamadas de
  API descritas em JSON (`tools/api_tool.py`) e funções Python sandboxed
  (`tools/python_tool.py`, desligadas por padrão) — CRUD e teste (`/invoke`)
  via API e pela tela `/tools`. `agents/registry.py` resolve os nomes salvos
  no agente pros objetos reais do Agno em runtime.
- API REST síncrona (`POST /chat`, com `dependencies` opcionais) e streaming
  (`POST /chat/stream`, com tracing e `event: usage` de tokens ao final).
- **Observabilidade via Langfuse self-hosted** (`observability/tracing.py`):
  trace por execução com modelo, tools, tokens, custo, sessão e usuário;
  feedback 👍/👎 do console e `POST /observability/scores` para outros módulos;
  execuções e traces lidos pela própria API (`/observability/runs`,
  `/observability/runs/{run_id}/trace`) e exibidos no console (`/observability`,
  aba *Execuções* de cada agente) — a porta do Langfuse nem fica exposta na rede.
- Collections de documentos via pgvector, com pipeline de ingestão completo
  (`documents/collections.py` + rotas nativas do AgentOS em `/knowledge/*`,
  mais o atalho `/collections/{name}/documents` para texto simples).
- Memória semântica via Mem0, plugável por agente através de pre/post hooks
  (`memory/mem0_backend.py` + `memory/mem0_hooks.py`) — `memory_backend` é um
  campo por-agente (`"common"` ou `"mem0"`), configurável via `/agents`.
- Esqueleto pronto para evoluir: mensageria via Redis Streams (`messaging/`).
- **Todo o stack containerizado** (`Dockerfile` do backend, `frontend/Dockerfile`,
  `docker-compose.yml` orquestrando serviço, console, bancos e o Langfuse) —
  `docker compose up -d --build` sobe tudo.
- **Frontend Next.js** (`frontend/`): console único com sidebar — playground
  com histórico de conversas reidratado, agentes com versões/diff e
  integração, e base de conhecimento — como BFF na frente do `agent-service`.

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
  `agent_prompt_versions` é só leitura/auditoria — o console já oferece
  "restaurar no editor", que republica o texto antigo como uma versão nova. Um endpoint `POST /agents/{type}/versions/{v}/activate`
  fecharia isso.
- **Upload de arquivo por collection**: `POST /knowledge/content` hoje resolve
  a collection automaticamente porque só existe uma (`general`). Com mais de
  uma em `COLLECTION_NAMES`, o proxy em `frontend/src/app/api/knowledge/content/route.ts`
  precisa passar `knowledge_id` (e a tela `/knowledge`, deixar escolher a
  collection no upload) — a ingestão de texto já suporta isso via `/collections/{name}/documents`.
- **Auth no frontend**: hoje sem login, `user_id` só vive no `localStorage`
  do browser. Entra quando a plataforma tiver um sistema de auth definido.
- **Múltiplos provedores de LLM**: adicionar branches em `models/provider.py`
  para OpenAI, Anthropic e modelos locais (Ollama/vLLM).
- **Gerenciamento de modelo mais rico**: fallback entre provedores, custo,
  rate limiting por tenant.
- **Autenticação/multi-tenancy** para uso dentro da plataforma (AgentOS já
  suporta `authorization=True`/`authorization_config`).
- **Avaliação automática**: datasets e LLM-as-a-judge do Langfuse sobre os
  traces já coletados — a API de scores (`POST /observability/scores`) já é o
  ponto de entrada para notas vindas de fora.
- **CI/CD e deploy**: pipeline de testes + build de imagem, manifests de
  deploy (k8s ou equivalente da plataforma).
