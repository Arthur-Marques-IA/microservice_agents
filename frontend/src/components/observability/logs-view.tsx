"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, RefreshCw, X } from "lucide-react";
import type { RunStatus } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/primitives";
import { Select } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PERIODS, usePeriodSince, type Period } from "@/components/observability/period-filter";
import { RUN_STATUS_OPTIONS } from "@/components/observability/run-status";
import { RunsTable, useRunsPager } from "@/components/observability/runs-table";
import { SessionsTable } from "@/components/observability/sessions-table";
import { StatsPanel } from "@/components/observability/stats-panel";
import { PageBody, PageHeader } from "@/components/workspace/page-header";
import { useWorkspace } from "@/components/workspace/workspace-provider";

interface Filters {
  agentType: string;
  status: RunStatus | "";
  period: Period;
}

/**
 * Logs da plataforma: sessões e execuções de qualquer agente, com gráficos e
 * filtros — o substituto interno da UI do Langfuse. `userId`/`sessionId` chegam
 * de links (ex.: o inspector do chat) e entram como um filtro fixo, removível.
 */
export function LogsView({ userId, sessionId }: { userId?: string; sessionId?: string }) {
  const router = useRouter();
  const { agents, observability } = useWorkspace();
  const [filters, setFilters] = useState<Filters>({ agentType: "", status: "", period: "7d" });
  const [tab, setTab] = useState<"sessions" | "runs">(sessionId ? "runs" : "sessions");
  const since = usePeriodSince(filters.period);

  const params = useMemo(() => {
    const p: Record<string, string> = {};
    if (filters.agentType) p.agent_type = filters.agentType;
    if (filters.status) p.status = filters.status;
    if (userId) p.user_id = userId;
    if (sessionId) p.session_id = sessionId;
    if (since) p.since = since;
    return p;
  }, [filters.agentType, filters.status, userId, sessionId, since]);

  const runsPager = useRunsPager(params);

  if (!observability.enabled) {
    return (
      <>
        <PageHeader title="Logs" />
        <PageBody>
          <Card>
            <EmptyState
              icon={Activity}
              title="Logs desligados"
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
      ? { label: "Sessão", value: sessionId }
      : null;

  return (
    <>
      <PageHeader
        title="Logs"
        description="Sessões e execuções de todos os agentes — pelo console, pela API ou por outros módulos."
        actions={
          <Button variant="outline" size="sm" onClick={() => void runsPager.reload()} disabled={runsPager.state === "loading"}>
            <RefreshCw className={runsPager.state === "loading" ? "animate-spin" : undefined} />
            Atualizar
          </Button>
        }
      />
      <PageBody className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          {fixedFilter && (
            <span className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-surface px-3 text-sm">
              {fixedFilter.label}: <span className="max-w-40 truncate font-mono text-xs">{fixedFilter.value}</span>
              <button
                type="button"
                onClick={() => router.push("/logs")}
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
          <Select
            aria-label="Filtrar por período"
            value={filters.period}
            onChange={(e) => setFilters((f) => ({ ...f, period: e.target.value as Filters["period"] }))}
            wrapperClassName="w-40"
          >
            {PERIODS.map((period) => (
              <option key={period.value} value={period.value}>
                {period.label}
              </option>
            ))}
          </Select>
          {filtered && (
            <Button variant="ghost" size="sm" onClick={() => setFilters((f) => ({ ...f, agentType: "", status: "" }))}>
              Limpar filtros
            </Button>
          )}
        </div>

        <StatsPanel params={params} />

        <Tabs value={tab} onValueChange={(value) => setTab(value as typeof tab)}>
          <TabsList>
            <TabsTrigger value="sessions">Sessões</TabsTrigger>
            <TabsTrigger value="runs">Execuções</TabsTrigger>
          </TabsList>
          <TabsContent value="sessions" className="mt-3">
            <SessionsTable params={params} />
          </TabsContent>
          <TabsContent value="runs" className="mt-3">
            <RunsTable
              items={runsPager.items}
              state={runsPager.state}
              error={runsPager.error}
              cursor={runsPager.cursor}
              loadingMore={runsPager.loadingMore}
              onLoadMore={() => void runsPager.loadMore()}
              onRetry={() => void runsPager.reload()}
              emptyTitle={filtered || fixedFilter ? "Nenhuma execução com esses filtros" : "Nenhuma execução registrada"}
              showAgentColumn
            />
          </TabsContent>
        </Tabs>
      </PageBody>
    </>
  );
}
