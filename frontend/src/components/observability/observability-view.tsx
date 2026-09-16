"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, RefreshCw, X } from "lucide-react";
import type { RunStatus } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/primitives";
import { Select } from "@/components/ui/select";
import { RUN_STATUS_OPTIONS } from "@/components/observability/run-status";
import { RunsTable, useRunsPager } from "@/components/observability/runs-table";
import { PageBody, PageHeader } from "@/components/workspace/page-header";
import { useWorkspace } from "@/components/workspace/workspace-provider";

interface Filters {
  agentType: string;
  status: RunStatus | "";
}

/**
 * Todas as execuções da plataforma, de qualquer agente — o substituto interno
 * da UI do Langfuse. `userId`/`sessionId` chegam de links (ex.: o inspector do
 * chat) e entram como um filtro fixo, removível.
 */
export function ObservabilityView({ userId, sessionId }: { userId?: string; sessionId?: string }) {
  const router = useRouter();
  const { agents, observability } = useWorkspace();
  const [filters, setFilters] = useState<Filters>({ agentType: "", status: "" });

  const params = useMemo(() => {
    const p: Record<string, string> = {};
    if (filters.agentType) p.agent_type = filters.agentType;
    if (filters.status) p.status = filters.status;
    if (userId) p.user_id = userId;
    if (sessionId) p.session_id = sessionId;
    return p;
  }, [filters, userId, sessionId]);

  const pager = useRunsPager(params);

  if (!observability.enabled) {
    return (
      <>
        <PageHeader title="Observabilidade" />
        <PageBody>
          <Card>
            <EmptyState
              icon={Activity}
              title="Observabilidade desligada"
              description="Configure LANGFUSE_PUBLIC_KEY e LANGFUSE_SECRET_KEY no agent-service para registrar as execuções."
            />
          </Card>
        </PageBody>
      </>
    );
  }

  const filtered = Boolean(filters.agentType || filters.status);
  const fixedFilter = userId
    ? { label: "Usuário", value: userId }
    : sessionId
      ? { label: "Conversa", value: sessionId }
      : null;

  return (
    <>
      <PageHeader
        title="Observabilidade"
        description="Todas as execuções de todos os agentes — pelo console, pela API ou por outros módulos."
        actions={
          <Button variant="outline" size="sm" onClick={() => void pager.reload()} disabled={pager.state === "loading"}>
            <RefreshCw className={pager.state === "loading" ? "animate-spin" : undefined} />
            Atualizar
          </Button>
        }
      />
      <PageBody className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {fixedFilter && (
            <span className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-surface px-3 text-sm">
              {fixedFilter.label}: <span className="max-w-40 truncate font-mono text-xs">{fixedFilter.value}</span>
              <button
                type="button"
                onClick={() => router.push("/observability")}
                className="text-muted-foreground hover:text-foreground"
                aria-label={`Remover filtro de ${fixedFilter.label.toLowerCase()}`}
              >
                <X className="size-3.5" />
              </button>
            </span>
          )}
          <Select
            aria-label="Filtrar por agente"
            value={filters.agentType}
            onChange={(e) => setFilters((f) => ({ ...f, agentType: e.target.value }))}
            wrapperClassName="w-48"
          >
            <option value="">Todos os agentes</option>
            {agents.map((agent) => (
              <option key={agent.agent_type} value={agent.agent_type}>
                {agent.name}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Filtrar por status"
            value={filters.status}
            onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value as Filters["status"] }))}
            wrapperClassName="w-40"
          >
            <option value="">Todos os status</option>
            {RUN_STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          {filtered && (
            <Button variant="ghost" size="sm" onClick={() => setFilters({ agentType: "", status: "" })}>
              Limpar filtros
            </Button>
          )}
        </div>

        <RunsTable
          items={pager.items}
          state={pager.state}
          error={pager.error}
          cursor={pager.cursor}
          loadingMore={pager.loadingMore}
          onLoadMore={() => void pager.loadMore()}
          onRetry={() => void pager.reload()}
          emptyTitle={filtered || fixedFilter ? "Nenhuma execução com esses filtros" : "Nenhuma execução registrada"}
          showAgentColumn
        />
      </PageBody>
    </>
  );
}
