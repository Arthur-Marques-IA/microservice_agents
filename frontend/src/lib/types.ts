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
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  usage?: UsageMetrics;
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
