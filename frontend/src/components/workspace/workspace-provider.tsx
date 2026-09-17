"use client";

import {
  ReactNode,
  SetStateAction,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { errorMessage, requestJson } from "@/lib/http";
import { toDate } from "@/lib/format";
import { useUserId } from "@/lib/use-local-storage";
import type {
  AgentDefinition,
  ModelCredential,
  ModelProviderSummary,
  ObservabilityConfig,
  Paginated,
  SessionSummary,
  ToolSummary,
} from "@/lib/types";

interface SessionsState {
  userId: string;
  data: SessionSummary[];
  error: string | null;
}

interface WorkspaceContextValue {
  /** Definições de agente carregadas pelo layout (server) — atualizadas via `router.refresh()`. */
  agents: AgentDefinition[];
  availableTools: ToolSummary[];
  collections: string[];
  /** URL do agent-service para exemplos de integração. */
  publicApiUrl: string;
  backendReachable: boolean;
  /** Langfuse: se o tracing está ligado e onde abrir o projeto. */
  observability: ObservabilityConfig;
  /** Catálogo de provedores de modelo — atualizado via `router.refresh()`. */
  modelProviders: ModelProviderSummary[];
  /** Credenciais de modelo cadastradas pelo layout (server) — atualizadas via `router.refresh()`. */
  modelCredentials: ModelCredential[];
  userId: string;
  sessions: SessionSummary[];
  sessionsLoading: boolean;
  sessionsError: string | null;
  refreshSessions: () => Promise<void>;
  renameSession: (sessionId: string, name: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  getAgent: (agentType?: string | null) => AgentDefinition | undefined;
  commandOpen: boolean;
  setCommandOpen: (open: SetStateAction<boolean>) => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

function byRecentActivity(a: SessionSummary, b: SessionSummary) {
  return toDate(b.updated_at ?? b.created_at).getTime() - toDate(a.updated_at ?? a.created_at).getTime();
}

/**
 * Estado compartilhado por todas as áreas do console: agentes, conversas do
 * usuário (sessões do AgentOS) e a paleta de comandos. É o que conecta o
 * playground, os agentes e a base de conhecimento numa única aplicação.
 */
export function WorkspaceProvider({
  agents,
  availableTools,
  collections,
  publicApiUrl,
  backendReachable,
  observability,
  modelProviders,
  modelCredentials,
  children,
}: {
  agents: AgentDefinition[];
  availableTools: ToolSummary[];
  collections: string[];
  publicApiUrl: string;
  backendReachable: boolean;
  observability: ObservabilityConfig;
  modelProviders: ModelProviderSummary[];
  modelCredentials: ModelCredential[];
  children: ReactNode;
}) {
  const userId = useUserId();
  const [sessionsState, setSessionsState] = useState<SessionsState | null>(null);
  const [commandOpen, setCommandOpen] = useState(false);

  const refreshSessions = useCallback(async () => {
    if (!userId) return;
    const params = new URLSearchParams({
      user_id: userId,
      limit: "100",
      sort_by: "updated_at",
      sort_order: "desc",
    });
    try {
      const page = await requestJson<Paginated<SessionSummary>>(`/api/sessions?${params}`, {
        fallbackError: "Falha ao carregar conversas",
      });
      setSessionsState({ userId, data: [...page.data].sort(byRecentActivity), error: null });
    } catch (err) {
      setSessionsState((prev) => ({
        userId,
        data: prev?.userId === userId ? prev.data : [],
        error: errorMessage(err),
      }));
    }
  }, [userId]);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  const renameSession = useCallback(
    async (sessionId: string, name: string) => {
      await requestJson(
        `/api/sessions/${encodeURIComponent(sessionId)}/rename?${new URLSearchParams({ user_id: userId })}`,
        { method: "POST", json: { session_name: name }, fallbackError: "Falha ao renomear conversa" }
      );
      setSessionsState(
        (prev) =>
          prev && {
            ...prev,
            data: prev.data.map((s) => (s.session_id === sessionId ? { ...s, session_name: name } : s)),
          }
      );
    },
    [userId]
  );

  const deleteSession = useCallback(
    async (sessionId: string) => {
      await requestJson(
        `/api/sessions/${encodeURIComponent(sessionId)}?${new URLSearchParams({ user_id: userId })}`,
        { method: "DELETE", fallbackError: "Falha ao excluir conversa" }
      );
      setSessionsState(
        (prev) => prev && { ...prev, data: prev.data.filter((s) => s.session_id !== sessionId) }
      );
    },
    [userId]
  );

  const getAgent = useCallback(
    (agentType?: string | null) => (agentType ? agents.find((a) => a.agent_type === agentType) : undefined),
    [agents]
  );

  const currentSessions = sessionsState && sessionsState.userId === userId ? sessionsState : null;

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      agents,
      availableTools,
      collections,
      publicApiUrl,
      backendReachable,
      observability,
      modelProviders,
      modelCredentials,
      userId,
      sessions: currentSessions?.data ?? [],
      sessionsLoading: currentSessions === null,
      sessionsError: currentSessions?.error ?? null,
      refreshSessions,
      renameSession,
      deleteSession,
      getAgent,
      commandOpen,
      setCommandOpen,
    }),
    [
      agents,
      availableTools,
      collections,
      publicApiUrl,
      backendReachable,
      observability,
      modelProviders,
      modelCredentials,
      userId,
      currentSessions,
      refreshSessions,
      renameSession,
      deleteSession,
      getAgent,
      commandOpen,
    ]
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace precisa estar dentro de <WorkspaceProvider>");
  return ctx;
}
