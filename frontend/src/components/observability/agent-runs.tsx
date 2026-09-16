"use client";

import { useMemo, useState } from "react";
import { Activity, RefreshCw } from "lucide-react";
import type { PromptVersion, RunStatus } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, SectionHeading } from "@/components/ui/primitives";
import { Select } from "@/components/ui/select";
import { RUN_STATUS_OPTIONS } from "@/components/observability/run-status";
import { RunsTable, useRunsPager } from "@/components/observability/runs-table";
import { useWorkspace } from "@/components/workspace/workspace-provider";

interface Filters {
  version: string;
  status: RunStatus | "";
}

/** Aba "Execuções" da página do agente — todas as chamadas a ele, de qualquer origem. */
export function AgentRuns({ agentType, versions }: { agentType: string; versions: PromptVersion[] }) {
  const { observability } = useWorkspace();
  const [filters, setFilters] = useState<Filters>({ version: "", status: "" });

  const params = useMemo(() => {
    const p: Record<string, string> = { agent_type: agentType };
    if (filters.version) p.prompt_version = filters.version;
    if (filters.status) p.status = filters.status;
    return p;
  }, [agentType, filters]);

  const pager = useRunsPager(params);

  if (!observability.enabled) {
    return (
      <Card>
        <EmptyState
          icon={Activity}
          title="Observabilidade desligada"
          description="Configure LANGFUSE_PUBLIC_KEY e LANGFUSE_SECRET_KEY no agent-service para registrar as execuções."
        />
      </Card>
    );
  }

  const filtered = Boolean(filters.version || filters.status);

  return (
    <div className="flex flex-col gap-3">
      <SectionHeading
        title="Execuções"
        description="Cada chamada ao agente — pelo console, pela API ou por outros módulos — com latência, tokens, custo e feedback."
        action={
          <Button variant="outline" size="sm" onClick={() => void pager.reload()} disabled={pager.state === "loading"}>
            <RefreshCw className={pager.state === "loading" ? "animate-spin" : undefined} />
            Atualizar
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Select
          aria-label="Filtrar por versão do prompt"
          value={filters.version}
          onChange={(e) => setFilters((f) => ({ ...f, version: e.target.value }))}
          wrapperClassName="w-40"
        >
          <option value="">Todas as versões</option>
          {versions.map((v) => (
            <option key={v.version} value={v.version}>
              Prompt v{v.version}
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
          <Button variant="ghost" size="sm" onClick={() => setFilters({ version: "", status: "" })}>
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
        emptyTitle={filtered ? "Nenhuma execução com esses filtros" : "Nenhuma execução registrada"}
      />
    </div>
  );
}
