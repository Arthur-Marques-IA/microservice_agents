import { Badge } from "@/components/ui/badge";
import type { ContentStatus } from "@/lib/types";

const labels: Record<ContentStatus, { label: string; variant: "muted" | "success" | "warning" | "destructive" }> = {
  processing: { label: "Processando...", variant: "muted" },
  completed: { label: "Concluído", variant: "success" },
  partial: { label: "Parcial", variant: "warning" },
  failed: { label: "Falhou", variant: "destructive" },
};

export function StatusBadge({ status }: { status: ContentStatus }) {
  const { label, variant } = labels[status];
  return <Badge variant={variant}>{label}</Badge>;
}
