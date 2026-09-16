import type { MemoryBackend, ToolKind } from "@/lib/types";

export interface ModelOption {
  provider: string;
  id: string;
  label: string;
}

/** Modelos oferecidos no formulário — espelha o que `models/provider.py` sabe montar. */
export const MODEL_OPTIONS: ModelOption[] = [
  { provider: "google", id: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
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
