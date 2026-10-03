"use client";

import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { errorMessage, requestJson } from "@/lib/http";
import { formatNumber } from "@/lib/format";
import type { ProcedureFunnel } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { SectionHeading, Skeleton } from "@/components/ui/primitives";
import { STAGE_TYPE_META } from "@/components/chat/procedure-progress";

/**
 * Funil de um agente procedural (`GET /agents/{t}/procedures`): quantas conversas
 * estão paradas em cada etapa. É onde se vê em que ponto as pessoas desistem —
 * uma etapa com muita gente parada costuma ser pergunta confusa ou dado difícil.
 * Os testes do Playground (dry_run) ficam de fora.
 */
export function ProcedureFunnelPanel({ agentType }: { agentType: string }) {
  const [funnel, setFunnel] = useState<ProcedureFunnel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    requestJson<ProcedureFunnel>(`/api/agents/${encodeURIComponent(agentType)}/procedures`, {
      fallbackError: "Falha ao carregar o funil",
    })
      .then((result) => !cancelled && setFunnel(result))
      .catch((err) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [agentType]);

  const max = Math.max(1, ...(funnel?.stages.map((s) => s.sessions) ?? []), funnel?.done ?? 0);

  return (
    <div className="flex flex-col gap-3">
      <SectionHeading
        title="Funil por etapa"
        description="Conversas paradas em cada etapa e quantas concluíram. Testes em dry_run não contam."
      />
      <Card className="p-5">
        {error ? (
          <p className="text-[13px] text-destructive">{error}</p>
        ) : !funnel ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-4/5" />
          </div>
        ) : funnel.total === 0 ? (
          <p className="text-[13px] text-muted-foreground">
            Nenhuma conversa ainda (fora os testes). O funil aparece quando o agente começar a atender.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {funnel.stages.map((stage, i) => {
              const Icon = STAGE_TYPE_META[stage.type].icon;
              return (
                <FunnelRow
                  key={stage.id}
                  label={`${i + 1}. ${stage.goal || stage.id}`}
                  icon={<Icon className="size-3.5 text-muted-foreground" />}
                  value={stage.sessions}
                  max={max}
                />
              );
            })}
            <FunnelRow
              label="Concluídas"
              icon={<Check className="size-3.5 text-success" />}
              value={funnel.done}
              max={max}
              done
            />
            {funnel.orphaned > 0 && (
              <li className="text-xs text-warning">
                {formatNumber(funnel.orphaned)} conversa(s) paradas numa etapa que não existe mais (o agente foi editado).
              </li>
            )}
          </ul>
        )}
      </Card>
    </div>
  );
}

function FunnelRow({
  label,
  icon,
  value,
  max,
  done = false,
}: {
  label: string;
  icon: React.ReactNode;
  value: number;
  max: number;
  done?: boolean;
}) {
  return (
    <li className="grid grid-cols-[minmax(0,14rem)_1fr_3rem] items-center gap-3 text-[13px]">
      <span className="flex min-w-0 items-center gap-1.5">
        {icon}
        <span className="truncate">{label}</span>
      </span>
      <span className="h-2 overflow-hidden rounded-full bg-muted">
        <span
          className={done ? "block h-full rounded-full bg-success" : "block h-full rounded-full bg-primary"}
          style={{ width: `${(value / max) * 100}%` }}
        />
      </span>
      <span className="text-right tabular-nums">{formatNumber(value)}</span>
    </li>
  );
}
