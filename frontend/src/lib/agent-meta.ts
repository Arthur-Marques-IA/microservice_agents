import type { MemoryBackend, ToolKind } from "@/lib/types";

export interface ModelOption {
  provider: string;
  id: string;
  label: string;
}

/**
 * Modelos oferecidos no formulário — espelha o que `models/provider.py` sabe
 * montar. Só aparecem no seletor os provedores cadastrados e habilitados em
 * `/models` (ver `agent-form.tsx`); `google` sempre aparece, mesmo sem chave
 * salva, pelo fallback antigo via `GOOGLE_API_KEY` no ambiente.
 */
export const MODEL_OPTIONS: ModelOption[] = [
  { provider: "google", id: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
  { provider: "google", id: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
  { provider: "openai", id: "gpt-4.1", label: "GPT-4.1" },
  { provider: "openai", id: "gpt-4.1-mini", label: "GPT-4.1 Mini" },
  { provider: "openai", id: "gpt-4o-mini", label: "GPT-4o Mini" },
  { provider: "anthropic", id: "claude-sonnet-4-5", label: "Claude Sonnet 4.5" },
  { provider: "anthropic", id: "claude-haiku-4-5", label: "Claude Haiku 4.5" },
  { provider: "ollama", id: "llama3.1", label: "Llama 3.1 (Ollama)" },
  { provider: "ollama", id: "qwen2.5", label: "Qwen 2.5 (Ollama)" },
];

export const DEFAULT_MODEL = MODEL_OPTIONS[0];

export function modelLabel(modelId?: string | null): string {
  if (!modelId) return `${DEFAULT_MODEL.label} (padrão)`;
  return MODEL_OPTIONS.find((m) => m.id === modelId)?.label ?? modelId;
}

export const MEMORY_BACKENDS: Record<MemoryBackend, { label: string; description: string }> = {
  common: {
    label: "Comum",
    description: "Histórico de sessão e memórias do usuário no Postgres, gerenciados pelo Agno.",
  },
  mem0: {
    label: "Mem0",
    description: "Soma memória semântica via Mem0 à memória comum. Requer MEM0_ENABLED no backend.",
  },
};

export const TOOL_KIND_META: Record<ToolKind, { label: string; description: string }> = {
  builtin: { label: "Padrão", description: "Uma toolkit pronta do Agno (busca, calculadora...)." },
  api: { label: "API", description: "Chama uma API HTTP existente, descrita em JSON — sem código." },
  python: { label: "Python", description: "Uma função Python enviada por você, executada num namespace restrito." },
};

/** Valida o JSON do campo `dependencies` do chat. */
export function parseDependencies(text: string): {
  value: Record<string, unknown> | null;
  error: string | null;
  count: number;
} {
  if (!text.trim()) return { value: null, error: null, count: 0 };
  try {
    const parsed: unknown = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { value: null, error: 'Use um objeto JSON, ex.: {"nome": "Maria"}', count: 0 };
    }
    const value = parsed as Record<string, unknown>;
    return { value, error: null, count: Object.keys(value).length };
  } catch (err) {
    return { value: null, error: `JSON inválido: ${(err as Error).message}`, count: 0 };
  }
}
