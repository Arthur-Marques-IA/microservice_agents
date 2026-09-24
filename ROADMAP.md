# Roadmap do Kuro (agent-service)

> Feito a partir da leitura do código em 2026-09-18 (commit `298a869`). Complementa a seção
> "Roadmap (fase 2+)" do README: reordena os itens de lá, acrescenta o que não aparecia e diz o que cortar.

## 1. Onde o produto está

**Já tem, e bem feito:**

- Agentes dinâmicos em Postgres, resolvidos sem restart, com versão de prompt e diff no console.
- Três formatos de tool (builtin, API descrita em JSON, Python). Cada parâmetro declara a origem
  (`model`/`dependency`/`const`), o que impede que um CPF passe pelo modelo. Isso é um diferencial real.
- Contrato de integração derivado dos dados (`/agents/{t}/integration`): a documentação não diverge do código.
- Dois tipos de agente: `conversational` e `analysis` (one-shot com `response_schema` validado).
- Anexos multimodais, RAG por collection, Mem0 plugável e a "nota de feedback" (um agent.md do admin).
- Observabilidade completa via Langfuse, sem ninguém precisar abrir a UI do Langfuse.
- CLI `kuro` pensada para outras IAs (`--json`, códigos de saída, `--no-input`, `AGENTS.md`).

**Falta, em ordem de gravidade:**

| Lacuna | Evidência | Por que importa |
|---|---|---|
| ~~Nenhuma autenticação~~ | **feito (parcial)** — `api/auth.py`: chave de API com escopos `runtime`/`admin`, por middleware (cobre também as rotas do AgentOS, onde a conversa está). Falta a tabela `api_keys` com várias chaves, revogação e `last_used_at`: hoje são duas chaves de ambiente, o tamanho certo para um tenant |
| ~~SSRF nas tools de API~~ | **feito** — `tools/egress.py` resolve o destino e recusa loopback/privado/link-local antes de cada chamada, nos dois caminhos de rede (`kind="api"` e o `httpx` das tools Python), com `TOOL_EGRESS_ALLOWLIST` para o host interno legítimo |
| Sem migrações | `agents/store.py::_add_missing_columns` faz `ALTER TABLE` à mão, já com 4 casos | Vai quebrar na primeira mudança de tipo ou de constraint |
| ~~Sem CI~~ | **feito** — `.github/workflows/ci.yml`: pytest, lint e build do frontend, e build das duas imagens, em todo push e PR |
| Versionamento parcial | só `instructions` gera `prompt_version`; mudar modelo ou tools não gera. A nota de feedback ganhou histórico e rollback próprios, mas numa linha separada | O trace grava `prompt-v{N}`, então uma regressão causada por troca de modelo fica invisível — e é preciso cruzar duas linhas do tempo para achar uma causada pelas regras |
| ~~RAG preso ao Google~~ | **feito** — `documents/embedder.py`: cada collection escolhe o embedder na criação (`google`/`openai`/`ollama`) e a chave sai de `/model-credentials`, como a do modelo. Fixo depois de criada de propósito: a tabela de vetores é de um embedder só |
| Modo só-terminal fica sem logs | com o Langfuse desligado, `kuro runs` não tem dados (o `health` avisa) | É exatamente o usuário que você quer atender com a "UI opcional" — que agora existe (profiles `ui`/`observability`), o que torna o trace store local da §4.1 mais urgente, não menos |

## 2. Posicionamento (para guiar as escolhas)

> **"Infra de agentes validada, operável por outro agente em poucas linhas."**

Três superfícies com papéis bem separados: **API** para integrar (contrato estável), **CLI/MCP** para
operar e corrigir, **UI** opcional para inspecionar. Toda feature nova deveria chegar primeiro na API +
CLI e só depois na UI. A paridade entre as três está fechada e documentada como matriz no README
(ver §6 para o que sobrou de fora e por quê).

A palavra que sustenta o produto é **validada**. Você já tem as peças (versões, traces, scores), mas
falta o ciclo que as une: *mudei o agente → provo que não piorou → publico*. A §5 cuida disso.

---

## 3. Horizonte 0: fundação (bloqueia o resto; ~2–3 semanas)

1. ~~**Autenticação por API key com escopos.**~~ **Feito em parte** (`api/auth.py`): duas chaves de
   ambiente (`ADMIN_API_KEY`, `RUNTIME_API_KEY`) com os escopos abaixo, cobrando por middleware para
   alcançar também as rotas do AgentOS (`/sessions`, `/knowledge/...`), que uma dependência por router
   deixaria de fora. A CLI lê `KURO_API_KEY` e o BFF do Next injeta a chave admin server-side. **Falta**
   a tabela `api_keys` (hash, escopos, tenant, `last_used_at`) para várias chaves e revogação sem
   restart — necessário assim que houver mais de um consumidor ou mais de um tenant.
   Contexto original: tabela `api_keys` (hash, escopos, tenant, `last_used_at`).
   Escopos mínimos:
   - `runtime`: `/chat`, `/analyze`, `/chat/stream`, scores. É o que os outros módulos recebem.
   - `admin`: CRUD de agentes, tools, credenciais, collections e leitura de traces. É o que CLI/UI usam.

   A CLI lê `KURO_API_KEY`. O BFF do Next injeta a key no server-side, como já faz com a URL.
   Quando isso existir, `CUSTOM_PYTHON_TOOLS_ENABLED` passa a fazer algum sentido.
2. **Decidir multi-tenancy agora, antes de existir dado.** `agent_type` é PK global, e o mesmo vale
   para tools, collections e credenciais. Mesmo que haja um tenant só, crie a coluna `tenant_id`
   (default `'default'`) e PKs compostas. Fazer isso depois exige migrar 5 tabelas com dados.
3. **Alembic.** Uma migração inicial que reflete o schema atual e o fim de `_add_missing_columns`.
4. ~~**CI (GitHub Actions).**~~ **Feito** (`.github/workflows/ci.yml`): pytest, `npm run lint`,
   `npm run build` e build das duas imagens. Sem `ruff` por enquanto — não está nas dependências de
   dev nem configurado, e adicioná-lo junto com a CI misturaria "passar a rodar os testes" com
   "formatar o repo inteiro".
5. ~~**Proteção de egress nas tools de API.**~~ **Feito** (`tools/egress.py`): resolve o DNS e recusa
   loopback, privado, link-local, multicast e reservado, com `TOOL_EGRESS_ALLOWLIST` por host. A
   checagem roda com a URL já montada, porque um parâmetro `location="path"` pode compor o host. O
   `httpx` das tools Python passa pelo mesmo controle — sem isso a trava seria enfeite. Falta a parte
   por tenant, que depende do item 2. Limite conhecido: DNS rebinding (checamos e o httpx resolve de
   novo ao conectar); fechar isso é papel de um egress firewall no ambiente.
6. **Tirar I/O síncrono do event loop.** `api/routes.py::chat` é `async`, mas `_resolve` faz
   consultas síncronas no Postgres: `get_definition`, `get_feedback_note` (duas vezes: no stamp e no
   build) e um `get_tool` por tool, ou seja N+2 round-trips bloqueantes por mensagem. Opções, da mais
   barata para a mais completa:
   - envolver em `run_in_threadpool`;
   - uma query só, com join, que devolve os stamps;
   - cache em memória com invalidação por `LISTEN/NOTIFY` do Postgres, que funciona com vários workers.

## 4. Horizonte 1: as suas duas ideias

### 4.1 UI opcional ("liga/desliga")

Custa pouco, porque o frontend já é um serviço separado que só consome a API. **Não faça isso com flag
no código, use `profiles` do Compose.** O peso real nem é a UI: é o Langfuse (ClickHouse + MinIO +
Redis + worker, ~16 GB recomendados). Quem quer só terminal quer os dois desligados.

**Feito.** `frontend` está em `profiles: ["ui"]` e os cinco serviços do Langfuse em
`profiles: ["observability"]`; `LANGFUSE_ENABLED` passou a ter default `false` no `agent-service`,
como a ressalva abaixo exigia. `docker compose up -d` sobe três serviços; o comando completo sobe nove. Há ainda um profile
`tls`, que põe um Caddy na frente com certificado do Let's Encrypt e renovação automática — sem
ele a chave de API trafegaria em texto claro, o que inviabilizava o serviço ser chamado por
outra plataforma em rede real.

```bash
docker compose up -d                                   # núcleo: postgres, redis, agent-service
docker compose --profile ui --profile observability up -d   # completo
```

Para ficar redondo:

- **Desligar o tracing junto com o profile.** Só remover os containers não basta. `LANGFUSE_ENABLED`
  tem default `true` e o compose passa as chaves ao `agent-service` de qualquer jeito, então
  `configure_tracing()` continua instrumentando e cada run tenta exportar para um host que não existe
  (timeout de 20 s). No `agent-service`, use `LANGFUSE_ENABLED: ${LANGFUSE_ENABLED:-false}` e ligue a
  variável só no comando completo. Sem isso, o modo enxuto fica mais lento e cheio de erro no log, o
  contrário do que ele promete.
- **`kuro up [--ui] [--observability]` / `kuro down` / `kuro status`**: um wrapper do compose,
  para quem opera tudo pela CLI. Grave a escolha em `.kuro/config.toml`.
- **Preço do modo enxuto: um trace store local.** `observability/trace_store.py` já é uma interface.
  Crie uma implementação em Postgres com tabelas `runs` e `run_spans`, alimentada pelo próprio
  `traced_run_events` (agente, versão, tokens, latência, status, tool calls). Isso resolve três
  problemas de uma vez:
  1. `kuro runs` funciona sem Langfuse;
  2. `/observability/sessions` e `/stats` deixam de "varrer um lote e agregar em memória" (limitação
     citada no README);
  3. "taxa de 👍 por versão do prompt", que o README diz exigir "um índice próprio", passa a ser
     um `GROUP BY`.

  O Langfuse vira um exportador *adicional* para quem quer a análise profunda.
- Com a UI desligada, a CLI precisa cobrir tudo. Ver a tabela de paridade na §6.
- **TUI de verdade.** O que existe hoje (`1eb1049 CLI/TUI v1`) é o shell/REPL interativo do `kuro`
  (typer + rich + questionary), não uma interface de tela cheia. Para quem desliga a UI, o próximo
  passo natural é um `kuro dash` em [Textual](https://textual.textualize.io): execuções chegando ao
  vivo, funil das etapas, gasto de tokens e trace de um run navegável. Ele depende do trace store
  local acima (H3).

### 4.2 Agente procedural (etapas)

**Verificação no Agno 3.0.9 instalado:**

- `agno/workflow` (Step/Router/Loop/Condition) é um pipeline que roda até o fim. Não foi feito para
  esperar o usuário responder entre uma etapa e outra.
- O HITL do Agno (`requires_confirmation` / `requires_user_input` + `continue_run`) pausa **dentro de
  um run, no nível da tool**. Isso serve para "confirme antes de eu executar a ação", mas não para ser
  o motor de etapas de uma conversa em que cada turno é um `/chat` novo.

**Recomendação:** uma máquina de estados determinística, no nosso código, com o estado numa tabela
própria: `procedure_runs(agent_type, session_id, stage, slots, status, updated_at)`. O `session_state`
do Agno é carregado da sessão a cada run (`agent/_run.py` → `run_context.session_state`), então serve
para *injetar* a etapa e os slots no contexto. Mas a fonte da verdade precisa ser consultável: o funil
por etapa vira um `GROUP BY stage`, e o produto não fica dependente da semântica de sessão do Agno. O LLM faz só duas coisas: extrair dados da mensagem (saída estruturada) e redigir a
resposta. Quem decide avançar, voltar ou concluir é o servidor. É isso que torna o agente
"infra validada", e não um prompt comprido pedindo "siga as etapas".

`kind="procedural"`, com uma coluna nova `stages`:

```json
{
  "agent_type": "abertura-chamado",
  "kind": "procedural",
  "stages": [
    { "id": "identificacao",
      "goal": "Obter CPF e nome do cliente",
      "fields": [ {"name": "cpf", "type": "string", "required": true, "pattern": "^\\d{11}$"},
                  {"name": "nome", "type": "string", "required": true} ],
      "prefill_from_dependencies": true },
    { "id": "problema",
      "goal": "Entender o problema",
      "fields": [ {"name": "categoria", "type": "string", "enum": ["internet","tv","fatura"]},
                  {"name": "descricao", "type": "string", "required": true} ],
      "tools": ["consulta_contrato"] },
    { "id": "confirmacao", "type": "confirm" },
    { "id": "abrir", "type": "action", "tool": "abrir_chamado", "on_success": "done" }
  ],
  "on_complete": { "emit": "redis", "stream": "kuro:procedures" }
}
```

Regras de design:

- **Reaproveite o que já existe.** `fields` usa o mesmo formato de `dependency_fields`/`response_schema`
  (e o mesmo `validate_field_specs`). A extração de cada etapa usa `build_response_model`, que já monta
  o schema do agente `analysis`. As etapas `action` chamam tools de API com `source: "dependency"`, e
  os slots coletados entram como dependências.
- **O estado da sessão não pode ficar no `Agent` em cache.** `agents/registry.py` guarda um `Agent`
  por `agent_type`. A etapa atual e os slots são lidos de `procedure_runs` a cada run, e as instruções
  da etapa entram por run (`session_state`/contexto adicional), nunca na instância compartilhada.
- **A confirmação é montada a partir dos slots, sem LLM.** Um template ("Confirma: CPF ***.456.789-00,
  categoria internet…?") impede que o modelo "confirme" um dado que não coletou.
- **Correções e volta atrás:** se o usuário disser "na verdade o CPF é outro", a extração detecta o
  campo já preenchido, o servidor volta para a etapa dona do campo e invalida as etapas seguintes.
- **Pular etapa quando o dado já chegou:** se quem chama mandou `cpf` em `dependencies`, a etapa de
  identificação fica pronta de saída.
- **O contrato de resposta cresce sem quebrar:** `ChatResponse.state = {stage, collected, missing,
  done, result}`. O módulo integrador sabe quando acabou sem precisar interpretar o texto.
- **Ao concluir,** o resultado estruturado vai para o Redis Stream / webhook. Esse é o primeiro uso
  real de `messaging/` (ver §8).
- **Observabilidade:** cada transição de etapa vira um span/evento. `kuro runs show` mostra a trilha
  `identificacao → problema → confirmacao → abrir`, o que ajuda muito a depurar onde os usuários
  desistem (funil por etapa na UI).
- **UI:** um stepper no inspector do chat. **CLI:** `kuro chat` mostra `[2/4 problema] faltando: descricao`.

## 5. Horizonte 2: "validada" de verdade (o diferencial)

1. **Replay / avaliação de regressão:** `kuro eval <agente> --against v7 --last 50`. O comando reexecuta
   as últimas N entradas reais (ou um dataset salvo) na versão candidata e compara com a atual usando
   um LLM-juiz + as regras do `response_schema`. Na saída mostra um relatório e o código de saída diz
   se piorou. É o recurso que fecha a narrativa "o Claude Code altera o agente e prova que não
   quebrou". O `POST /observability/scores` já está pronto para receber as notas.
2. **Versionar a configuração inteira, não só o prompt.** Cada `PUT` que muda comportamento (instruções,
   modelo, tools, collection, nota de feedback, etapas) gera um snapshot imutável `agent_versions`.
   O trace registra `config-v{N}`.
3. **Canais `draft` / `prod` e fixação de versão.** `/chat` aceita `agent_type: "suporte@12"` ou
   `"suporte@draft"`. A promoção vira `kuro agents promote suporte 12`, com rollback de um comando
   (resolve o item "rollback" do README de um jeito mais útil que um `activate`). Opcional: canário
   por % de sessões.
4. **A nota de feedback precisa de governança.** Hoje ela é sobrescrita (`upsert_feedback_note`), fica
   sem histórico, passa a valer na próxima mensagem de produção e o merge usa sempre o modelo padrão.
   Sugestões:
   - histórico + diff;
   - `--dry-run` que mostra a nota resultante antes de salvar;
   - modo "proposta", em que a nota cai em `draft` e passa pelo `kuro eval` antes de ir para prod;
   - agrupar vários 👎 comentados num merge só (lote semanal), em vez de um merge por feedback.
5. **Servidor MCP do Kuro.** Mesmas operações da CLI expostas como tools MCP (`create_agent`,
   `chat_agent`, `list_runs`, `run_eval`...). O Claude Code e outros agentes passam a operar sem
   passar pelo shell nem interpretar stdout. O `AGENTS.md` continua sendo a documentação, e o MCP
   vira o transporte. Vale publicar também uma *skill* do Claude Code com as receitas.
6. **Agentes como código (GitOps).** `kuro export ./kuro/` gera um YAML por agente, tool e collection.
   `kuro plan ./kuro/` mostra o diff contra o servidor (estilo Terraform) e `kuro apply ./kuro/`
   aplica. Os agentes passam a ser revisados em PR, a CI roda `kuro eval` e o próprio repo vira a
   auditoria. `kuro schema agent` publica o JSON Schema para validação no editor.

## 6. Usabilidade

**Paridade CLI × UI** (necessária para a UI poder ser desligada):

| Capacidade | API | UI | CLI |
|---|---|---|---|
| Criar/editar tools | ✅ | ✅ | ✅ `tools apply -f` / `set` / `delete` / `get --editable` |
| Sessões (listar, ver transcrição, apagar) | ✅ | ✅ | ✅ `kuro sessions list/show/delete` |
| Estatísticas (KPIs, custo por agente) | ✅ | ✅ | ✅ `kuro runs stats` |
| Seguir execuções ao vivo | — | — | ✅ `kuro runs tail --agent x` (consulta repetida, não um stream) |
| Restaurar versão | via PUT | ✅ | ✅ `kuro agents rollback <t> <v>` |
| Upload de arquivo para collection | ✅ | ✅ | ✅ `collections add -f doc.pdf` |
| Documentos indexados (listar, apagar) | ✅ | ✅ | ✅ `collections docs` / `rm-doc` |
| Regras de feedback (ver, editar, histórico, rollback) | ✅ | ✅ aba Aprendizado | ✅ `agents feedback --show/--remove/--versions/--rollback` |
| Rodar um agente analista | ✅ | ✅ página Análise | ✅ `kuro analyze` |

A paridade fechou. O upload de arquivo saiu do `/knowledge/content` do AgentOS
(que só alimenta a collection padrão) para uma rota própria,
`POST /collections/{nome}/files`, que resolve a collection por nome e usa o
embedder dela. Sobraram três exceções, todas com motivo declarado no README:
indexar por **URL** (ainda no pipeline do AgentOS, só na padrão), **`runs tail`**
e **testar uma chave antes de salvá-la**.

`kuro sessions` usa as rotas de sessão do AgentOS (Postgres), não
`/observability/sessions`, justamente para continuar funcionando no modo
só-terminal. Já `runs stats` e `runs tail` leem o Langfuse: sem ele, saem com
código 1 e a mensagem da API — o que reforça a necessidade do trace store local
da §4.1.

**Outros pontos:**

- `kuro agents new --template {suporte|extrator|procedural}`: parte de um exemplo que funciona em vez
  de um JSON vazio. Os templates também servem de documentação viva.
- `--dry-run` em `apply`, `set` e `feedback`: mostra o diff e as validações sem gravar. Faz muita
  diferença quando quem opera é outra IA.
- Mensagens de erro com a próxima ação sugerida (já acontece em várias rotas, então vale virar padrão),
  por exemplo `"hint": "kuro agents set x dependency_fields=..."`.
- Custo visível no fluxo: `kuro chat` e o `ChatResponse` síncrono devolvem `usage` e custo estimado
  (hoje só o stream envia `usage`).
- Um **orçamento por agente** (tokens/dia ou R$/mês), com alerta e bloqueio, fica simples depois do
  trace store local.

## 7. Otimizações técnicas na stack

| Onde | Problema | Sugestão |
|---|---|---|
| `agents/base.py` | Todo agente `common` liga `enable_agentic_memory` + `add_memories_to_context`, o que traz chamadas extras ao LLM. ~~Com `mem0`, as duas memórias rodam em paralelo~~ (corrigido: o `mem0` agora substitui a memória do Agno) | Memória explícita em três modos: `none` / `agno` / `mem0`. A maioria dos agentes de atendimento com `user_id` efêmero não precisa de memória longa |
| `memory/mem0_backend.py` | `MemoryClient` é o Mem0 **hospedado**, então dados do cliente (CPF etc.) saem da sua infra. O post-hook salva só a mensagem do usuário, de forma síncrona | Mem0 OSS (`Memory`) sobre o mesmo pgvector, por questão de LGPD; salvar o par usuário/assistente; hook assíncrono em background |
| ~~`agents/base.py` + `/analyze`~~ | **corrigido**: o agente de análise recebia `db=get_db()` e cada chamada criava uma sessão `analyze-<uuid>` no Postgres, com o documento inteiro dentro | `db=None` em `kind="analysis"`. O Agno guarda todo acesso a sessão com `if agent.db is not None`, e a busca na collection não usa `agent.db`, então o RAG continua valendo |
| Anexos | O base64 fica no histórico da sessão e volta a cada turno (o `AGENTS.md` já avisa) | `POST /files` que devolve `file_id`, guardar em storage de objetos (o MinIO já está no compose) e no histórico manter só a referência |
| `documents/collections.py` | Embedder fixo em Gemini e `lru_cache` sem invalidação | Embedder e credencial por collection (usando o cofre), com invalidação igual à dos agentes |
| AgentOS no boot | Agentes e collections criados depois do boot não aparecem nas rotas do AgentOS | Se o playground do os.agno.com não for essencial, deixe o AgentOS só para ingestão, ou remova (ver §8) |
| Seleção de modelo | Ainda não há fallback (o README já prevê) | Com vários provedores já cadastrados, dá para ligar `fallback_models` por agente agora |
| Streaming | O `/chat` síncrono agrega o stream em memória | Timeout por run + cancelamento quando o cliente desconecta, e `max_tool_calls` por agente contra loops de tool |
| ~~Tool de API travando o event loop~~ | **corrigido**: o entrypoint era síncrono e o Agno chama entrypoint síncrono direto no caminho `async` (`Function.aexecute`), então uma chamada de 15s parava todas as requisições do worker | Entrypoint `async` com `httpx.AsyncClient` único — o pool também evita refazer o handshake TLS a cada chamada |
| Escala | Cache por processo | Com o `LISTEN/NOTIFY` do H0 dá para rodar com `--workers N` ou várias réplicas sem cache velho |

## 8. O que cortar ou não fazer

- **`messaging/redis_streams.py::consume_tasks`**: hoje é código morto que o README anuncia como
  "pronto para virar um worker". Ele tem um consumer fixo (`worker-1`), faz ack depois do `yield`
  (se o processo cair, a mensagem se perde) e não tem dead-letter. Ou vira o worker de jobs
  assíncronos (`POST /chat/async` → `job_id` + webhook, e evento de conclusão do agente procedural),
  ou sai. Um esqueleto documentado que ninguém chama engana quem lê o código.
- **Tools `python` enquanto não houver isolamento real.** O próprio código admite que o namespace
  restrito não é uma sandbox. As tools de API cobrem a maior parte dos casos. Se forem mantidas,
  precisam rodar em um container efêmero, sem rede e com limite de CPU/memória, e isso é um projeto à
  parte. Prefira esconder do produto até lá.

  Revisadas em 2026-09-22, sem mudar essa conclusão. Foram corrigidos os dois problemas com efeito
  operacional, e o resto virou documentação honesta no docstring do módulo:
  - o `httpx` das tools Python agora passa pelo controle de egress (era o desvio da trava nova);
  - o timeout não interrompe o código (Python não mata thread de fora) e todas as tools dividiam um
    pool de 8 workers, então **oito tools travadas paravam todas as tools Python do serviço**. Agora
    cada chamada roda na própria thread daemon, com teto de 32 simultâneas: a travada queima um slot,
    não a fila inteira.
  - continuam em aberto, e só o isolamento de verdade resolve: sem limite de memória/CPU
    (`[0] * 10**10` derruba o container) e `str.format` alcançando atributos (`"{0.__class__}"`),
    que vaza informação mas só produz texto.
- **Agente "orquestrador" genérico.** O procedural resolve o caso de uso concreto (fluxos guiados) com
  muito menos risco. Faça o orquestrador só quando existir um roteamento real entre agentes que o
  procedural não resolva.
- **Dependência do playground do os.agno.com.** Seu console já cobre isso. Manter o AgentOS só por ele
  traz a ressalva de "aparece só depois do restart".
- **Multi-provedor de embeddings antes do trace store local e da auth.** O ganho é menor que o dos itens do H0/H1.

## 9. Sequência sugerida

Os prazos são estimativas grosseiras para dar ordem de grandeza, não compromisso.

| Fase | Entregas | Resultado |
|---|---|---|
| **H0**, 2–3 sem. | CI, Alembic, `tenant_id`, API keys com escopos, bloqueio de egress, I/O fora do event loop | Pode ir para um ambiente compartilhado |
| **H1a**, 1 sem. | Profiles `ui`/`observability`, `kuro up/down/status`, trace store em Postgres | Modo "só terminal" completo |
| **H1b**, 3–4 sem. | Agente procedural + `state` no contrato + evento de conclusão (worker Redis de verdade) | Novo tipo de produto: fluxos guiados |
| **H2**, 4–6 sem. | Versão da config inteira, `draft/prod` + `@versão`, `kuro eval` (replay), governança da nota de feedback | "Validada" deixa de ser promessa |
| **H3**, contínuo | Servidor MCP, GitOps (`plan/apply` de diretório), templates, paridade CLI, `kuro dash` (TUI), orçamento por agente | Um agente de IA opera o Kuro de ponta a ponta |
