/** Anexo de `/chat` e `/analyze`: imagem, áudio, vídeo ou arquivo. */
export interface Attachment {
  content_base64?: string;
  url?: string;
  mime_type?: string | null;
  filename?: string | null;
}

export interface ChatRequest {
  agent_type: string;
  user_id: string;
  session_id: string;
  message: string;
  dependencies?: Record<string, unknown>;
  attachments?: Attachment[];
}

export interface AnalyzeRequest {
  agent_type: string;
  document: string;
  dependencies?: Record<string, unknown>;
  attachments?: Attachment[];
}

export interface AnalyzeResponse {
  agent_type: string;
  /** Validado contra o `response_schema` do agente. */
  result: Record<string, unknown>;
  run_id: string;
  trace_id?: string | null;
}

/** Uma regra da nota de comportamento (`GET /agents/{tipo}/feedback`). */
export interface FeedbackRule {
  id: string;
  texto: string;
}

export interface FeedbackNote {
  agent_type: string;
  /** Markdown derivado das regras — é o que entra nas instructions. */
  content: string;
  rules: FeedbackRule[];
  version: number;
  updated_at: string;
  /** Só na resposta do POST: o que o merge mudou. */
  diff?: Record<string, string[]> | null;
}

export interface FeedbackVersion {
  version: number;
  rules: FeedbackRule[];
  content: string;
  origin: string;
  created_at: string;
}

/** `GET /agents/{tipo}/integration` — o contrato que quem integra precisa. */
export interface DependencyContract {
  name: string;
  type: string;
  required: boolean;
  label: string;
  description: string;
  example: unknown;
  /** Tools do agente que consomem este campo — elas falham sem ele. */
  required_by_tools: string[];
}

export interface IntegrationContract {
  agent_type: string;
  name: string;
  kind: AgentKind;
  prompt_version: number;
  /** `/chat` num conversacional, `/analyze` num analista. */
  endpoint: string;
  chat_url: string;
  stream_url: string | null;
  response_schema: SchemaField[];
  dependencies: DependencyContract[];
  request_example: Record<string, unknown>;
  curl: string;
  warnings: string[];
}

export interface ChatResponse {
  agent_type: string;
  session_id: string;
  content: string;
  run_id: string;
  trace_id?: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  usage?: UsageMetrics;
  createdAt?: number;
  /** Resposta ainda em streaming. */
  pending?: boolean;
  /** Streaming interrompido pelo usuário. */
  stopped?: boolean;
  /** Mensagem de erro, quando a execução falhou. */
  error?: string;
  /** `run_id` da execução — chave do trace no Langfuse e do feedback. */
  runId?: string;
}

export interface SearchResult {
  content: string;
  metadata: Record<string, unknown> | null;
}

export type ContentStatus = "processing" | "completed" | "partial" | "failed";

export interface ContentStatusResponse {
  status: ContentStatus;
  status_message?: string | null;
}

export interface UploadedContent {
  id: string;
  name: string;
}

/** Item de `GET /knowledge/content` (AgentOS). */
export interface KnowledgeContent {
  id: string;
  name?: string | null;
  description?: string | null;
  type?: string | null;
  size?: string | null;
  metadata?: Record<string, unknown> | null;
  status?: ContentStatus | null;
  status_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PaginationMeta {
  page: number;
  limit: number;
  total_pages: number;
  total_count: number;
}

export interface Paginated<T> {
  data: T[];
  meta: PaginationMeta;
}

/** Item de `GET /sessions` (AgentOS) — uma conversa. */
export interface SessionSummary {
  session_id: string;
  session_name?: string | null;
  agent_id?: string | null;
  user_id?: string | null;
  total_tokens?: number | null;
  created_at: string;
  updated_at?: string | null;
}

/** Item de `GET /sessions/{id}/runs` (AgentOS) — uma troca pergunta/resposta. */
export interface SessionRun {
  run_id: string;
  parent_run_id?: string | null;
  agent_id?: string | null;
  status?: string | null;
  run_input?: unknown;
  content?: unknown;
  metrics?: UsageMetrics | null;
  created_at?: number | string | null;
}

export type MemoryBackend = "common" | "mem0";

export type DependencyFieldType = "string" | "integer" | "number" | "boolean";

/** Um campo de `dependencies` que o agente espera no `/chat` (ex.: `cpf`, obrigatório). */
export interface DependencyField {
  name: string;
  type: DependencyFieldType;
  label: string;
  description: string;
  required: boolean;
  default: unknown;
  /** Valores permitidos (não vale para boolean). */
  enum?: (string | number)[] | null;
}

export interface DependencyFieldInput {
  name: string;
  type?: DependencyFieldType;
  label?: string | null;
  description?: string | null;
  required?: boolean;
  default?: unknown;
}

export type AgentKind = "conversational" | "analysis";

/** Vocabulário de campo composto — o mesmo do backend (`field_schema.py`). */
export type FieldType = "string" | "integer" | "number" | "boolean" | "object" | "array";
export type ItemType = "string" | "integer" | "number" | "boolean" | "object";

/**
 * Campo de `response_schema` (agente `kind: "analysis"`) ou parâmetro composto
 * de tool. `object` exige `fields`, `array` exige `items` — sem isso o provedor
 * recusa o schema, então o backend responde 422 no cadastro.
 */
export interface SchemaField {
  name: string;
  type: FieldType;
  label?: string | null;
  description?: string | null;
  required?: boolean;
  default?: unknown;
  /** Valores permitidos: o modelo só pode devolver um deles (folhas, menos boolean). */
  enum?: (string | number)[] | null;
  fields?: SchemaField[] | null;
  items?: SchemaItem | null;
}

export interface SchemaItem {
  type: ItemType;
  fields?: SchemaField[] | null;
  enum?: (string | number)[] | null;
}

/** Parâmetros de geração (`models/params.py`); ausente = padrão do provedor. */
export interface ModelParams {
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  /** Só Gemini 2.5: 0 desliga o raciocínio (mais rápido e barato). */
  thinking_budget?: number;
}

export interface AgentDefinition {
  agent_type: string;
  name: string;
  kind: AgentKind;
  /** Só em `kind: "analysis"`: a forma do objeto que o `/analyze` devolve. */
  response_schema: SchemaField[];
  instructions: string[];
  tools: string[];
  model_provider: string | null;
  model_id: string | null;
  /** Credencial específica (`ModelCredential.id`) que este agente usa; `null` = a padrão do provedor. */
  model_credential_id: string | null;
  /** Collection de documentos que o agente pode consultar; `null` = sem base de conhecimento. */
  knowledge_collection: string | null;
  dependency_fields: DependencyField[];
  memory_backend: MemoryBackend;
  num_history_runs: number;
  model_params?: ModelParams | null;
  /** Tempo limite de uma execução; `null` = padrão do serviço (RUN_TIMEOUT_SECONDS). */
  timeout_seconds?: number | null;
  is_seed: boolean;
  prompt_version: number;
  created_at: string;
  updated_at: string;
}

export interface AgentDefinitionInput {
  agent_type: string;
  name: string;
  /** `num_history_runs` e `memory_backend` dão 422 em `kind: "analysis"`: um
   * agente one-shot não tem histórico nem memória. */
  kind?: AgentKind;
  response_schema?: SchemaField[];
  instructions: string[];
  tools?: string[];
  model_provider?: string | null;
  model_id?: string | null;
  model_credential_id?: string | null;
  knowledge_collection?: string | null;
  dependency_fields?: DependencyFieldInput[];
  memory_backend?: MemoryBackend;
  num_history_runs?: number;
  model_params?: ModelParams | null;
  timeout_seconds?: number | null;
}

export interface PromptVersion {
  version: number;
  instructions: string[];
  created_at: string;
}

/** Versão da configuração inteira (`GET /agents/{t}/revisions`) — o `agent_version` de cada run. */
export interface AgentRevision {
  version: number;
  config_hash: string;
  config: {
    instructions?: string[];
    model_provider?: string;
    model_id?: string;
    model_params?: ModelParams;
    timeout_seconds?: number;
    tools?: { tool_name: string; kind?: string; config_hash?: string; missing?: boolean }[];
    feedback_rules?: string[];
    response_schema?: SchemaField[];
    knowledge_collection?: string | null;
    [key: string]: unknown;
  };
  created_at: string;
  current: boolean;
}

export interface PromoteResult {
  agent: AgentDefinition;
  source: string;
  source_version: number;
  previous_version: number | null;
  agent_version: number;
  unchanged: boolean;
}

// -- Collections (bases de conhecimento) --------------------------------

/** `GET /collections/embedders` — quem pode gerar os vetores de uma collection. */
export interface EmbedderOption {
  provider: string;
  label: string;
  default_model_id: string;
  default_dimensions: number | null;
  requires_api_key: boolean;
  description: string;
  /** A credencial existe agora — sem isso, criar a collection dá 422. */
  configured: boolean;
}

export interface Collection {
  name: string;
  /** Fixo na criação: a tabela de vetores é de um embedder só. */
  embedder_provider: string;
  embedder_model: string;
  embedder_dimensions?: number | null;
  /** Coleção que o pipeline de upload do AgentOS (arquivo/URL) alimenta. */
  is_default: boolean;
  label: string;
  description: string | null;
  is_seed: boolean;
  /** Agentes com `knowledge_collection` apontando para cá. */
  agents_using: string[];
  created_at: string;
  updated_at: string;
}

// -- Tools ------------------------------------------------------------

export type ToolKind = "builtin" | "api" | "python";

/** `GET /tools` — uma tool disponível para os agentes usarem. */
export interface ToolSummary {
  tool_name: string;
  kind: ToolKind;
  label: string;
  description: string | null;
  config: Record<string, unknown>;
  enabled: boolean;
  is_seed: boolean;
  created_at: string;
  updated_at: string;
}

/** `GET /tools/{name}` — inclui introspecção best-effort (builtins têm várias funções). */
export interface ToolDetail extends ToolSummary {
  functions?: string[] | null;
  build_error?: string | null;
}

export interface ToolInput {
  tool_name: string;
  kind: ToolKind;
  label: string;
  description?: string | null;
  config: Record<string, unknown>;
  enabled?: boolean;
}

export type ToolUpdateInput = Partial<Omit<ToolInput, "tool_name" | "kind">>;

export type BuiltinParamType = "string" | "integer" | "boolean";

export interface BuiltinParam {
  name: string;
  type: BuiltinParamType;
  label: string;
  description: string;
  required: boolean;
  secret: boolean;
  default: unknown;
}

/** `GET /tools/catalog` — toolkits padrão do Agno disponíveis para `kind: "builtin"`. */
export interface BuiltinCatalogEntry {
  builtin_id: string;
  label: string;
  description: string;
  params: BuiltinParam[];
}

/** Location de um parâmetro de tool `kind: "api"`. */
export type ApiParamLocation = "query" | "path" | "header" | "body";
export type ApiParamType = "string" | "integer" | "number" | "boolean" | "object" | "array";

/** De onde vem o valor do parâmetro (o backend assume "model" quando ausente). */
export type ApiParamSource = "model" | "dependency" | "const";

export interface ApiToolParam {
  name: string;
  type: ApiParamType;
  location: ApiParamLocation;
  description?: string;
  required?: boolean;
  source?: ApiParamSource;
  /** Campo de `dependencies` que preenche este parâmetro (`source: "dependency"`). */
  dependency?: string;
  /** Valor fixo (`source: "const"`). */
  value?: unknown;
  /** Obrigatório em `type: "object"` com `source: "model"`. */
  fields?: SchemaField[] | null;
  /** Obrigatório em `type: "array"` com `source: "model"`. */
  items?: SchemaItem | null;
}

export type ApiAuth =
  | { type: "none" }
  | { type: "bearer"; token: string }
  | { type: "api_key"; header: string; value: string }
  | { type: "basic"; username: string; password: string };

export interface ApiToolConfig {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  url: string;
  headers?: Record<string, string>;
  auth?: ApiAuth;
  parameters: ApiToolParam[];
  timeout_seconds?: number;
}

export interface PythonToolConfig {
  code: string;
  entrypoint: string;
  timeout_seconds?: number;
}

export interface ToolInvokeInput {
  arguments?: Record<string, unknown>;
  function_name?: string | null;
  /** Simula o `dependencies` do `/chat` para parâmetros `source: "dependency"`. */
  dependencies?: Record<string, unknown>;
}

export interface ToolInvokeResult {
  ok: boolean;
  result?: unknown;
  error?: string | null;
}

// -- Provedores e credenciais de modelo ----------------------------------

/** `GET /model-providers` — catálogo de provedores suportados + quantas credenciais cada um já tem. */
export interface ModelProviderSummary {
  provider: string;
  label: string;
  requires_api_key: boolean;
  supports_custom_base_url: boolean;
  default_model_id: string;
  docs_url: string;
  credential_count: number;
  configured_count: number;
}

/**
 * `GET /model-credentials` — uma chave cadastrada. Vários agentes podem
 * apontar pra mesma credencial; a mesma provider pode ter várias credenciais
 * (times/clientes diferentes). A chave nunca volta, só `key_hint`.
 */
export interface ModelCredential {
  id: string;
  provider: string;
  provider_label: string;
  label: string;
  configured: boolean;
  key_hint?: string | null;
  base_url?: string | null;
  enabled: boolean;
  last_tested_at?: string | null;
  last_test_ok?: boolean | null;
  last_test_message?: string | null;
  /** Nomes dos agentes que usam esta credencial hoje — pra avisar antes de excluir/desabilitar. */
  agents_using: string[];
  created_at: string;
  updated_at: string;
}

export interface ModelCredentialCreateInput {
  provider: string;
  label: string;
  api_key?: string;
  base_url?: string;
  enabled?: boolean;
}

export interface ModelCredentialUpdateInput {
  label?: string;
  api_key?: string;
  clear_api_key?: boolean;
  base_url?: string;
  enabled?: boolean;
}

export interface ModelCredentialTestInput {
  api_key?: string;
  base_url?: string;
}

export interface ModelCredentialTestResult {
  ok: boolean;
  message?: string | null;
  tested_at: string;
}

export interface UsageMetrics {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  reasoning_tokens?: number;
  cost?: number;
  duration?: number;
  [key: string]: unknown;
}

export type RunStatus = "success" | "error" | "interrupted";

/** Uma execução de agente, lida do Langfuse pelo backend (`GET /observability/agents/{type}/runs`). */
export interface RunSummary {
  run_id: string;
  trace_id: string;
  agent_type: string;
  agent_name?: string | null;
  prompt_version?: number | null;
  /** Versão da configuração inteira que rodou; `null` em runs antigos. */
  agent_version?: number | null;
  config_hash?: string | null;
  endpoint?: string | null;
  user_id?: string | null;
  session_id?: string | null;
  environment?: string | null;
  started_at: string;
  ended_at?: string | null;
  latency_ms?: number | null;
  status: RunStatus;
  status_message?: string | null;
  message?: string | null;
  output?: string | null;
  model?: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd?: number | null;
  /** `null` quando havia avaliações demais para contar na listagem — o trace tem a contagem exata. */
  feedback_up: number | null;
  feedback_down: number | null;
  /** Correlação mandada por quem chamou (ex.: `conversation_id`). */
  metadata?: Record<string, string>;
}

export interface RunPage {
  items: RunSummary[];
  next_cursor?: string | null;
}

/** Um span do trace (agente, chamada ao modelo, tool...). A árvore sai de `parent_id`. */
export interface TraceSpan {
  id: string;
  parent_id?: string | null;
  type: string;
  name: string;
  started_at: string;
  ended_at?: string | null;
  latency_ms?: number | null;
  level: string;
  status_message?: string | null;
  input?: unknown;
  output?: unknown;
  model?: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd?: number | null;
  metadata: Record<string, unknown>;
}

export interface TraceScore {
  id: string;
  name: string;
  value: number | boolean | string | null;
  data_type: string;
  source: string;
  comment?: string | null;
  user_id?: string | null;
  timestamp: string;
}

/** `GET /observability/runs/{run_id}/trace`. */
export interface RunTrace {
  run: RunSummary;
  spans: TraceSpan[];
  scores: TraceScore[];
  /** Decisão de referência (ex.: a do agente legado no modo shadow). */
  reference?: Record<string, unknown> | null;
}

/** `GET /observability/agreement` — concordância com a referência (modo shadow). */
export interface Agreement {
  agent_type: string;
  runs: number;
  skipped: number;
  full_match: number;
  rate: number;
  fields: { field: string; compared: number; matched: number; rate: number }[];
  by_version: { agent_version: number | null; runs: number; full_match: number; rate: number }[];
  disagreements: {
    run_id: string;
    agent_version: number | null;
    mismatches: { field: string; expected: unknown; actual: unknown }[];
  }[];
}

/** `GET /observability/config` — se as execuções são registradas, se o Langfuse está ligado e onde fica o projeto. */
export interface ObservabilityConfig {
  /** As execuções são registradas e podem ser lidas (sempre, com o trace store local). */
  enabled: boolean;
  /** O exportador do Langfuse está ligado. */
  langfuse?: boolean;
  /** Projeto na UI do Langfuse (ex.: http://localhost:3100/project/agent-service). */
  project_url: string | null;
}

/** Item de `GET /observability/sessions` — execuções de uma sessão agregadas (tokens, custo, feedback). */
export interface LogSessionSummary {
  session_id: string;
  user_id?: string | null;
  agent_types: string[];
  run_count: number;
  started_at: string;
  last_activity: string;
  total_tokens: number;
  cost_usd?: number | null;
  error_count: number;
  feedback_up: number | null;
  feedback_down: number | null;
}

export interface LogSessionPage {
  items: LogSessionSummary[];
  /** Quantas execuções-raiz entraram na varredura — ver docstring do backend. */
  scanned: number;
}

export interface RunStatsBucket {
  date: string;
  runs: number;
  errors: number;
  total_tokens: number;
  cost_usd?: number | null;
}

/** `GET /observability/stats` — série diária + contagem por status para os gráficos dos Logs. */
export interface RunStats {
  buckets: RunStatsBucket[];
  status_counts: Partial<Record<RunStatus, number>>;
  total_runs: number;
  total_tokens: number;
  total_cost_usd?: number | null;
  avg_latency_ms?: number | null;
  scanned: number;
}
