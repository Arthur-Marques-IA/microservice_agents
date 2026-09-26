"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { GraduationCap, MessageSquare } from "lucide-react";
import type { RunSummary } from "@/lib/types";
import { CopyButton } from "@/components/ui/copy-button";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, RelativeTime, SectionHeading, Skeleton } from "@/components/ui/primitives";
import { Select } from "@/components/ui/select";
import { TeachAgent } from "@/components/agents/teach-agent";
import { RunsTable, useRunsPager } from "@/components/observability/runs-table";
import { StatsPanel } from "@/components/observability/stats-panel";
import { PageBody, PageHeader } from "@/components/workspace/page-header";
import { useWorkspace } from "@/components/workspace/workspace-provider";

/**
 * Visão completa de uma sessão: a conversa, o feedback para o agente, gráficos e
 * todas as execuções.
 *
 * A conversa vem das execuções registradas (mensagem e resposta de cada run), e
 * não do Playground: ela aparece para qualquer sessão — de outro navegador, da
 * CLI, de um sistema integrado ou de um agente analista, que nem guarda
 * conversa. "Abrir no Playground" só aparece quando a sessão é deste navegador
 * (mesmo `user_id`) e de um agente conversacional; nos outros casos o Playground
 * não teria como abri-la, e o link levava a "Conversa não encontrada".
 */
export function SessionDetailView({ sessionId }: { sessionId: string }) {
  const { observability, userId, getAgent } = useWorkspace();
  const params = useMemo(() => ({ session_id: sessionId }), [sessionId]);
  const runsPager = useRunsPager(params);
  const runs = runsPager.items;
  const firstRun = runs[runs.length - 1];

  const conversationalAgents = useMemo(
    () =>
      [...new Set(runs.map((r) => r.agent_type))].filter((type) => getAgent(type)?.kind === "conversational"),
    [runs, getAgent]
  );
  const ownedByThisBrowser = runs.length > 0 && runs.every((r) => r.user_id === userId);
  const canOpenInPlayground = ownedByThisBrowser && conversationalAgents.length > 0;

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
          canOpenInPlayground ? (
            <Link href={`/chat/${encodeURIComponent(sessionId)}`} className={buttonVariants({ variant: "outline" })}>
              <MessageSquare />
              <span className="hidden sm:inline">Continuar no Playground</span>
            </Link>
          ) : undefined
        }
      />
      <PageBody className="flex flex-col gap-6">
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          <Transcript runs={runs} loading={runsPager.state === "loading"} />
          {conversationalAgents.length > 0 && <TeachCard sessionId={sessionId} agentTypes={conversationalAgents} />}
        </div>
        {observability.enabled && <StatsPanel params={params} showTrend={false} />}
        <RunsTable
          items={runs}
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

/** Saída de analista é JSON: vira um bloco formatado em vez de uma linha só. */
function formatOutput(output: string): { text: string; json: boolean } {
  const trimmed = output.trim();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      return { text: JSON.stringify(JSON.parse(trimmed), null, 2), json: true };
    } catch {
      // não era JSON de verdade — mostra como veio
    }
  }
  return { text: output, json: false };
}

function Transcript({ runs, loading }: { runs: RunSummary[]; loading: boolean }) {
  const ordered = useMemo(() => [...runs].reverse(), [runs]);

  if (loading) return <Skeleton className="h-48" />;
  if (ordered.length === 0) {
    return (
      <Card>
        <EmptyState icon={MessageSquare} title="Sem mensagens" description="Nenhuma execução registrada nesta sessão." />
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <SectionHeading
        title="Conversa"
        description="Cada mensagem recebida e o que o agente respondeu, na ordem — das execuções registradas."
      />
      <Card className="flex flex-col gap-4 p-4">
        {ordered.map((run) => {
          const output = run.output ? formatOutput(run.output) : null;
          return (
            <div key={run.run_id} className="flex flex-col gap-2">
              {run.message && (
                <div className="self-end max-w-[85%] whitespace-pre-wrap rounded-xl bg-muted px-3 py-2 text-[13px]">
                  {run.message}
                </div>
              )}
              <div className="flex max-w-[92%] flex-col gap-1">
                {output ? (
                  output.json ? (
                    <pre className="overflow-x-auto rounded-lg border border-border bg-surface p-3 font-mono text-[12px]">
                      {output.text}
                    </pre>
                  ) : (
                    <p className="whitespace-pre-wrap text-[13px]">{output.text}</p>
                  )
                ) : (
                  <p className="text-[13px] text-muted-foreground">
                    {run.status === "success" ? "(sem resposta registrada)" : run.status_message || run.status}
                  </p>
                )}
                <Link
                  href={`/runs/${encodeURIComponent(run.run_id)}`}
                  className="text-[11px] text-muted-foreground hover:underline"
                >
                  {run.agent_name ?? run.agent_type} · <RelativeTime date={run.started_at} /> · ver trace
                </Link>
              </div>
            </div>
          );
        })}
      </Card>
    </div>
  );
}

function TeachCard({ sessionId, agentTypes }: { sessionId: string; agentTypes: string[] }) {
  const { getAgent } = useWorkspace();
  const [chosen, setChosen] = useState(agentTypes[0]);
  const agentType = agentTypes.includes(chosen) ? chosen : agentTypes[0];

  return (
    <div className="flex flex-col gap-3">
      <SectionHeading
        title={
          <span className="flex items-center gap-2">
            <GraduationCap className="size-4" /> Ensinar o agente
          </span>
        }
        description="Diga o que deveria ter sido diferente nesta conversa; vira uma regra do agente."
      />
      <Card className="flex flex-col gap-3 p-4">
        {agentTypes.length > 1 && (
          <Select aria-label="Agente" value={agentType} onChange={(e) => setChosen(e.target.value)}>
            {agentTypes.map((type) => (
              <option key={type} value={type}>
                {getAgent(type)?.name ?? type}
              </option>
            ))}
          </Select>
        )}
        <TeachAgent agentType={agentType} sessionId={sessionId} />
        <Link
          href={`/agents/${encodeURIComponent(agentType)}?tab=feedback`}
          className="text-xs text-muted-foreground hover:underline"
        >
          Ver as regras de {getAgent(agentType)?.name ?? agentType}
        </Link>
      </Card>
    </div>
  );
}
