export interface ChatRequest {
  agent_type: string;
  user_id: string;
  session_id: string;
  message: string;
  dependencies?: Record<string, unknown>;
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
}

export interface DependencyFieldInput {
  name: string;
  type?: DependencyFieldType;
  label?: string | null;
  description?: string | null;
  required?: boolean;
  default?: unknown;
}

export interface AgentDefinition {
  agent_type: string;
  name: string;
  instructions: string[];
  tools: string[];
  model_provider: string | null;
  model_id: string | null;
  /** Credencial específica (`ModelCredential.id`) que este agente usa; `null` = a padrão do provedor. */
  model_credential_id: string | null;
  dependency_fields: DependencyField[];
  memory_backend: MemoryBackend;
  num_history_runs: number;
  is_seed: boolean;
  prompt_version: number;
  created_at: string;
  updated_at: string;
}

export interface AgentDefinitionInput {
  agent_type: string;
  name: string;
  instructions: string[];
  tools?: string[];
  model_provider?: string | null;
  model_id?: string | null;
  model_credential_id?: string | null;
  dependency_fields?: DependencyFieldInput[];
  memory_backend?: MemoryBackend;
  num_history_runs?: number;
}

export interface PromptVersion {
  version: number;
  instructions: string[];
  created_at: string;
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

export interface ApiToolParam {
  name: string;
  type: ApiParamType;
  location: ApiParamLocation;
  description?: string;
  required?: boolean;
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
}

/** `GET /observability/config` — se o Langfuse está ligado e onde fica o projeto. */
export interface ObservabilityConfig {
  enabled: boolean;
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
