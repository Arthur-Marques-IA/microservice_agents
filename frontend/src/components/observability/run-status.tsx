import { CircleAlert, CircleCheck, CirclePause, ThumbsDown, ThumbsUp } from "lucide-react";
import { cn } from "@/lib/cn";
import type { RunStatus } from "@/lib/types";
import { Badge, type BadgeVariant } from "@/components/ui/badge";

const STATUS: Record<RunStatus, { label: string; variant: BadgeVariant; icon: typeof CircleCheck }> = {
  success: { label: "Sucesso", variant: "success", icon: CircleCheck },
  error: { label: "Erro", variant: "destructive", icon: CircleAlert },
  interrupted: { label: "Interrompido", variant: "warning", icon: CirclePause },
};

export const RUN_STATUS_OPTIONS = Object.entries(STATUS).map(([value, { label }]) => ({
  value: value as RunStatus,
  label,
}));

export function RunStatusBadge({ status, title }: { status: RunStatus; title?: string | null }) {
  const { label, variant, icon: Icon } = STATUS[status];
  return (
    <Badge variant={variant} title={title ?? undefined}>
      <Icon aria-hidden />
      {label}
    </Badge>
  );
}

/** Contagem de 👍/👎 do run; "—" quando ninguém avaliou, "?" quando a contagem é desconhecida. */
export function FeedbackCount({
  up,
  down,
  className,
}: {
  up: number | null;
  down: number | null;
  className?: string;
}) {
  if (up === null || down === null) {
    return (
      <span className={cn("text-muted-foreground", className)} title="Avaliações demais no período para contar aqui — abra o trace">
        ?
      </span>
    );
  }
  if (!up && !down) return <span className={cn("text-muted-foreground", className)}>—</span>;
  return (
    <span
      className={cn("inline-flex items-center gap-2 tabular-nums", className)}
      aria-label={`${up} positivo(s), ${down} negativo(s)`}
    >
      {up > 0 && (
        <span className="inline-flex items-center gap-0.5 text-success">
          <ThumbsUp className="size-3" aria-hidden />
          {up}
        </span>
      )}
      {down > 0 && (
        <span className="inline-flex items-center gap-0.5 text-destructive">
          <ThumbsDown className="size-3" aria-hidden />
          {down}
        </span>
      )}
    </span>
  );
}
