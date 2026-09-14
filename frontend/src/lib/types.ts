export interface ChatRequest {
  agent_type: string;
  user_id: string;
  session_id: string;
  message: string;
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
