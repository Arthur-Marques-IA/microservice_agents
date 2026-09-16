"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Activity, ChevronRight, RefreshCw } from "lucide-react";
import { errorMessage, requestJson } from "@/lib/http";
import { formatCost, formatMs, formatNumber } from "@/lib/format";
import type { PromptVersion, RunPage, RunStatus, RunSummary } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, RelativeTime, SectionHeading, Skeleton, Spinner } from "@/components/ui/primitives";
import { Select } from "@/components/ui/select";
import { FeedbackCount, RUN_STATUS_OPTIONS, RunStatusBadge } from "@/components/observability/run-status";
import { useWorkspace } from "@/components/workspace/workspace-provider";

const PAGE_SIZE = 25;

interface Filters {
  version: string;
  status: RunStatus | "";
}

/** Execuções do agente (todas as origens: console, API, outros módulos), lidas do Langfuse pelo backend. */
export function AgentRuns({ agentType, versions }: { agentType: string; versions: PromptVersion[] }) {
  const { observability } = useWorkspace();
  const [filters, setFilters] = useState<Filters>({ version: "", status: "" });
  const [items, setItems] = useState<RunSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPage = useCallback(
    async (pageCursor: string | null) => {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
      if (filters.version) params.set("prompt_version", filters.version);
      if (filters.status) params.set("status", filters.status);
      if (pageCursor) params.set("cursor", pageCursor);
      return requestJson<RunPage>(`/api/observability/agents/${encodeURIComponent(agentType)}/runs?${params}`, {
        fallbackError: "Falha ao carregar execuções",
      });
    },
    [agentType, filters]
  );

  const reload = useCallback(async () => {
    setState("loading");
    setError(null);
    try {
      const page = await fetchPage(null);
      setItems(page.items);
      setCursor(page.next_cursor ?? null);
      setState("ready");
    } catch (err) {
      setError(errorMessage(err));
      setState("error");
    }
  }, [fetchPage]);

  useEffect(() => {
    if (!observability.enabled) return;
    // Carga inicial e recarga ao mudar filtros.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
  }, [observability.enabled, reload]);

  async function loadMore() {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const page = await fetchPage(cursor);
      setItems((prev) => [...prev, ...page.items]);
      setCursor(page.next_cursor ?? null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoadingMore(false);
    }
  }

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
          <Button variant="outline" size="sm" onClick={() => void reload()} disabled={state === "loading"}>
            <RefreshCw className={state === "loading" ? "animate-spin" : undefined} />
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

      {state === "loading" ? (
        <Card className="flex flex-col gap-3 p-4" aria-busy="true" aria-label="Carregando execuções">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </Card>
      ) : state === "error" ? (
        <Card>
          <EmptyState
            icon={Activity}
            title="Não foi possível carregar as execuções"
            description={error}
            action={
              <Button variant="outline" size="sm" onClick={() => void reload()}>
                Tentar de novo
              </Button>
            }
          />
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon={Activity}
            title={filtered ? "Nenhuma execução com esses filtros" : "Nenhuma execução registrada"}
            description="Execuções recém-terminadas levam alguns segundos para aparecer."
            action={
              // Uma página pode vir vazia (traces de fora do serviço) e ainda haver mais.
              cursor && (
                <Button variant="outline" size="sm" onClick={() => void loadMore()} disabled={loadingMore}>
                  {loadingMore && <Spinner />}
                  Carregar mais
                </Button>
              )
            }
          />
        </Card>
      ) : (
        <>
          <Card className="overflow-hidden">
            <div className="scrollbar-thin overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="w-[36%] px-4 py-2.5 font-medium">Mensagem</th>
                    <th className="px-3 py-2.5 font-medium">Status</th>
                    <th className="px-3 py-2.5 font-medium">Versão</th>
                    <th className="px-3 py-2.5 text-right font-medium">Latência</th>
                    <th className="px-3 py-2.5 text-right font-medium">Tokens</th>
                    <th className="px-3 py-2.5 text-right font-medium">Custo</th>
                    <th className="px-3 py-2.5 font-medium">Feedback</th>
                    <th className="px-3 py-2.5 font-medium">Quando</th>
                    <th className="w-8" aria-hidden />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {items.map((run) => (
                    <RunRow key={run.run_id} run={run} />
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          {error && <p className="text-xs text-destructive">{error}</p>}
          {cursor && (
            <Button variant="outline" size="sm" className="self-center" onClick={() => void loadMore()} disabled={loadingMore}>
              {loadingMore && <Spinner />}
              Carregar mais
            </Button>
          )}
        </>
      )}
    </div>
  );
}

function RunRow({ run }: { run: RunSummary }) {
  const href = `/runs/${encodeURIComponent(run.run_id)}`;
  return (
    <tr className="group relative transition-colors hover:bg-accent/50">
      <td className="max-w-0 px-4 py-2.5">
        {/* O link cobre a linha inteira; as células ficam como texto normal para leitores de tela. */}
        <Link href={href} className="absolute inset-0" aria-label={`Abrir trace: ${run.message ?? run.run_id}`} />
        <p className="truncate font-medium">{run.message || <span className="text-muted-foreground">(sem mensagem)</span>}</p>
        <p className="truncate text-xs text-muted-foreground">
          {run.user_id ?? "—"}
          {run.endpoint && <> · {run.endpoint}</>}
        </p>
      </td>
      <td className="px-3 py-2.5">
        <RunStatusBadge status={run.status} title={run.status_message} />
      </td>
      <td className="px-3 py-2.5">
        {run.prompt_version != null ? <Badge variant="outline">v{run.prompt_version}</Badge> : "—"}
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums">{formatMs(run.latency_ms)}</td>
      <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums">{run.total_tokens ? formatNumber(run.total_tokens) : "—"}</td>
      <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums">{formatCost(run.cost_usd)}</td>
      <td className="px-3 py-2.5 text-xs">
        <FeedbackCount up={run.feedback_up} down={run.feedback_down} />
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 text-xs text-muted-foreground">
        <RelativeTime date={run.started_at} />
      </td>
      <td className="pr-3 text-muted-foreground">
        <ChevronRight className="size-4 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
      </td>
    </tr>
  );
}
