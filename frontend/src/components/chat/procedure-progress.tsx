"use client";

import { Check, CircleAlert, ListChecks, Loader, Play, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/cn";
import type { ProcedureStage, ProcedureStageType, ProcedureState } from "@/lib/types";
import { Badge } from "@/components/ui/badge";

export const STAGE_TYPE_META: Record<ProcedureStageType, { label: string; icon: typeof ListChecks }> = {
  collect: { label: "Coleta", icon: ListChecks },
  confirm: { label: "Confirmação", icon: ShieldCheck },
  action: { label: "Ação", icon: Play },
};

function display(value: unknown): string {
  if (typeof value === "boolean") return value ? "sim" : "não";
  if (value === null || value === undefined) return "—";
  return typeof value === "string" ? value : JSON.stringify(value);
}

/**
 * Faixa sob o cabeçalho do chat: em que etapa a conversa está e o que falta.
 * Sempre visível num agente procedural, mesmo com o inspector fechado.
 */
export function ProcedureStrip({
  state,
  stages,
  onOpen,
  loading = false,
}: {
  state: ProcedureState | null;
  stages: ProcedureStage[];
  onOpen: () => void;
  /** A conversa já tem mensagens e o estado ainda não chegou: "Etapa 1" seria mentira. */
  loading?: boolean;
}) {
  if (loading && !state) {
    return (
      <div className="flex w-full items-center gap-3 border-b border-border bg-surface px-4 py-2 text-[13px] text-muted-foreground">
        <Loader className="size-3.5 animate-spin" /> Carregando a etapa da conversa…
      </div>
    );
  }
  const total = state?.stages_total ?? stages.length;
  const index = state ? state.stage_index : 0;
  const current = state?.stages.find((s) => s.status === "current") ?? (state ? undefined : stages[0]);
  const missing = state?.missing.map((f) => f.label || f.name) ?? [];
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-3 border-b border-border bg-surface px-4 py-2 text-left text-[13px] hover:bg-accent/40"
      title="Ver as etapas e os dados coletados"
    >
      <span className="flex shrink-0 items-center gap-1" aria-hidden>
        {Array.from({ length: total }, (_, i) => (
          <span
            key={i}
            className={cn(
              "h-1.5 w-5 rounded-full",
              state?.done || i < index ? "bg-success" : i === index ? "bg-primary" : "bg-muted"
            )}
          />
        ))}
      </span>
      {state?.done ? (
        <span className="flex items-center gap-1.5 font-medium text-success">
          <Check className="size-3.5" /> Procedimento concluído
        </span>
      ) : (
        <span className="min-w-0 truncate">
          <span className="font-medium">
            Etapa {Math.min(index + 1, total)} de {total}
            {current ? ` · ${current.goal || current.id}` : ""}
          </span>
          {missing.length > 0 && <span className="text-muted-foreground"> — falta {missing.join(", ")}</span>}
          {state && Object.keys(state.invalid).length > 0 && (
            <span className="text-warning"> · valor inválido em {Object.keys(state.invalid).join(", ")}</span>
          )}
        </span>
      )}
    </button>
  );
}

/** As etapas, uma por linha, com o que cada uma coletou — para o inspector. */
export function ProcedureSteps({ state, stages }: { state: ProcedureState | null; stages: ProcedureStage[] }) {
  const statusOf = (id: string, i: number) =>
    state?.stages.find((s) => s.id === id)?.status ?? (i === 0 ? "current" : "pending");

  return (
    <ol className="flex flex-col">
      {stages.map((stage, i) => {
        const status = statusOf(stage.id, i);
        const Icon = STAGE_TYPE_META[stage.type].icon;
        const action = state?.actions[stage.id];
        const last = i === stages.length - 1;
        return (
          <li key={stage.id} className="relative flex gap-3 pb-4 last:pb-0">
            {!last && (
              <span
                className={cn("absolute left-[11px] top-6 h-[calc(100%-1.5rem)] w-px", status === "done" ? "bg-success/50" : "bg-border")}
                aria-hidden
              />
            )}
            <span
              className={cn(
                "flex size-6 shrink-0 items-center justify-center rounded-full border",
                status === "done" && "border-success bg-success/10 text-success",
                status === "current" && "border-primary bg-primary-soft text-primary",
                status === "pending" && "border-border text-muted-foreground"
              )}
            >
              {status === "done" ? <Check className="size-3.5" /> : <Icon className="size-3.5" />}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className={cn("text-[13px] font-medium", status === "pending" && "text-muted-foreground")}>
                  {stage.goal || stage.id}
                </span>
                <Badge variant="outline">{STAGE_TYPE_META[stage.type].label}</Badge>
                {status === "current" && <Badge>atual</Badge>}
              </div>
              {stage.type === "collect" && (
                <dl className="mt-1.5 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-xs">
                  {(stage.fields ?? []).map((field) => {
                    const value = state?.collected[field.name];
                    const invalid = state?.invalid[field.name];
                    return (
                      <div key={field.name} className="contents">
                        <dt className="text-muted-foreground">
                          {field.label || field.name}
                          {field.required && " *"}
                        </dt>
                        <dd className={cn("truncate text-right", invalid && "text-warning")} title={invalid ?? display(value)}>
                          {invalid ? `inválido: ${invalid}` : value === undefined ? "—" : display(value)}
                        </dd>
                      </div>
                    );
                  })}
                </dl>
              )}
              {stage.type === "action" && (
                <p className="mt-1 text-xs text-muted-foreground">
                  <span className="font-mono">{stage.tool}</span>
                  {action?.status === "running" && (
                    <span className="ml-1.5 inline-flex items-center gap-1">
                      <Loader className="size-3 animate-spin" /> executando
                    </span>
                  )}
                  {action?.status === "failed" && (
                    <span className="mt-0.5 flex items-start gap-1 text-destructive">
                      <CircleAlert className="mt-0.5 size-3 shrink-0" />
                      <span className="min-w-0 break-words">
                        falhou{action.attempts ? ` (tentativa ${action.attempts})` : ""}: {action.error}. Confirmar de novo tenta outra vez.
                      </span>
                    </span>
                  )}
                  {action?.status === "done" && (
                    <span className="mt-0.5 block break-words text-success">resultado: {display(action.result)}</span>
                  )}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
