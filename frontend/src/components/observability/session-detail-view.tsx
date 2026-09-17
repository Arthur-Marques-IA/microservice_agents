"use client";

import { useMemo } from "react";
import Link from "next/link";
import { MessageSquare } from "lucide-react";
import { CopyButton } from "@/components/ui/copy-button";
import { buttonVariants } from "@/components/ui/button";
import { RunsTable, useRunsPager } from "@/components/observability/runs-table";
import { StatsPanel } from "@/components/observability/stats-panel";
import { PageBody, PageHeader } from "@/components/workspace/page-header";
import { useWorkspace } from "@/components/workspace/workspace-provider";

/** Visão completa de uma sessão: gráficos e KPIs (`StatsPanel`) + todas as suas execuções. */
export function SessionDetailView({ sessionId }: { sessionId: string }) {
  const { observability } = useWorkspace();
  const params = useMemo(() => ({ session_id: sessionId }), [sessionId]);
  const runsPager = useRunsPager(params);
  const firstRun = runsPager.items[runsPager.items.length - 1];

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: "Logs", href: "/logs" },
          { label: "Sessão" },
        ]}
        title={
          <span className="inline-flex items-center gap-1.5 font-mono text-base">
            {sessionId}
            <CopyButton value={sessionId} label="Copiar id da sessão" className="size-6" />
          </span>
        }
        description={firstRun?.user_id ? `Usuário ${firstRun.user_id}` : undefined}
        actions={
          <Link href={`/chat/${encodeURIComponent(sessionId)}`} className={buttonVariants({ variant: "outline" })}>
            <MessageSquare />
            <span className="hidden sm:inline">Abrir conversa</span>
          </Link>
        }
      />
      <PageBody className="flex flex-col gap-4">
        {observability.enabled && <StatsPanel params={params} showTrend={false} />}
        <RunsTable
          items={runsPager.items}
          state={runsPager.state}
          error={runsPager.error}
          cursor={runsPager.cursor}
          loadingMore={runsPager.loadingMore}
          onLoadMore={() => void runsPager.loadMore()}
          onRetry={() => void runsPager.reload()}
          emptyTitle="Nenhuma execução encontrada para esta sessão"
          showAgentColumn
        />
      </PageBody>
    </>
  );
}
