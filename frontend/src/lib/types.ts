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

export interface AgentDefinition {
  agent_type: string;
  name: string;
  instructions: string[];
  tools: string[];
  model_provider: string | null;
  model_id: string | null;
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
  memory_backend?: MemoryBackend;
  num_history_runs?: number;
}

export interface PromptVersion {
  version: number;
  instructions: string[];
  created_at: string;
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

/** `GET /observability/config` — se o Langfuse está ligado e onde fica o projeto. */
export interface ObservabilityConfig {
  enabled: boolean;
  /** Projeto na UI do Langfuse (ex.: http://localhost:3100/project/agent-service). */
  project_url: string | null;
}
