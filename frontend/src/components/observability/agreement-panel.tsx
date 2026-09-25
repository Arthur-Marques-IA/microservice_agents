"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { GitCompareArrows } from "lucide-react";
import { cn } from "@/lib/cn";
import { errorMessage, requestJson } from "@/lib/http";
import type { Agreement } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { SectionHeading, Skeleton } from "@/components/ui/primitives";

function tone(rate: number) {
  return rate >= 0.95 ? "bg-success" : rate >= 0.8 ? "bg-warning" : "bg-destructive";
}

function percent(rate: number) {
  return `${Math.round(rate * 100)}%`;
}

function show(value: unknown) {
  return value === null || value === undefined ? "—" : typeof value === "string" ? value : JSON.stringify(value);
}

/**
 * Modo shadow: quanto a decisão deste agente concorda com a referência gravada
 * por quem chama (`POST /observability/references` — no Regente, a decisão do
 * agente legado). Por campo e por versão da configuração: é o número que diz
 * quando promover. Some quando não há referência nenhuma, para não poluir a aba
 * de agentes que não estão em shadow.
 */
export function AgreementPanel({ agentType, since }: { agentType: string; since?: string }) {
  const [data, setData] = useState<Agreement | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams({ agent_type: agentType });
    if (since) params.set("since", since);
    let cancelled = false;
    requestJson<Agreement>(`/api/observability/agreement?${params}`, { fallbackError: "Falha ao carregar concordância" })
      .then((result) => !cancelled && setData(result))
      .catch((err) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [agentType, since]);

  if (error) return <Card className="p-4 text-[13px] text-destructive">{error}</Card>;
  if (data === null) return <Skeleton className="h-28" />;
  if (data.runs === 0 && data.skipped === 0) return null;

  return (
    <div className="flex flex-col gap-3">
      <SectionHeading
        title={
          <span className="flex items-center gap-2">
            <GitCompareArrows className="size-4" /> Concordância com a referência (shadow)
          </span>
        }
        description="Decisão do agente × decisão gravada por quem chama (ex.: o agente legado), campo a campo."
      />
      <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
        <Card className="flex flex-col gap-1 p-4">
          <span className="text-3xl font-semibold tabular-nums">{percent(data.rate)}</span>
          <span className="text-[13px] text-muted-foreground">
            {data.full_match} de {data.runs} execuções concordam em tudo
          </span>
          {data.skipped > 0 && (
            <span className="text-xs text-muted-foreground">{data.skipped} sem saída comparável (erro ou timeout)</span>
          )}
          <div className="mt-3 flex flex-col gap-1 border-t border-border pt-3">
            {data.by_version.map((v) => (
              <div key={String(v.agent_version)} className="flex justify-between text-xs">
                <span className="text-muted-foreground">{v.agent_version ? `config v${v.agent_version}` : "sem versão"}</span>
                <span className="tabular-nums">
                  {v.full_match}/{v.runs} · {percent(v.rate)}
                </span>
              </div>
            ))}
          </div>
        </Card>
        <Card className="flex flex-col gap-2.5 p-4">
          {[...data.fields]
            .sort((a, b) => a.rate - b.rate)
            .map((f) => (
              <div key={f.field} className="grid grid-cols-[minmax(0,160px)_minmax(0,1fr)_72px] items-center gap-3 text-[13px]">
                <span className="truncate font-mono text-xs" title={f.field}>
                  {f.field}
                </span>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div className={cn("h-full rounded-full", tone(f.rate))} style={{ width: percent(f.rate) }} />
                </div>
                <span className="text-right text-xs tabular-nums text-muted-foreground">
                  {f.matched}/{f.compared}
                </span>
              </div>
            ))}
        </Card>
      </div>
      {data.disagreements.length > 0 && (
        <Card className="divide-y divide-border overflow-hidden">
          {data.disagreements.slice(0, 8).map((d) => (
            <Link
              key={d.run_id}
              href={`/runs/${encodeURIComponent(d.run_id)}`}
              className="flex flex-col gap-0.5 px-4 py-2.5 text-[13px] transition-colors hover:bg-accent/50"
            >
              <span className="font-mono text-[11px] text-muted-foreground">
                {d.run_id}
                {d.agent_version ? ` · config v${d.agent_version}` : ""}
              </span>
              {d.mismatches.map((m) => (
                <span key={m.field}>
                  <span className="font-mono text-xs">{m.field}</span>: referência <b>{show(m.expected)}</b>, agente{" "}
                  <b>{show(m.actual)}</b>
                </span>
              ))}
            </Link>
          ))}
        </Card>
      )}
    </div>
  );
}
