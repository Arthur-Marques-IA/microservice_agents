"use client";

import { useState } from "react";
import Link from "next/link";
import { Activity, ThumbsDown, ThumbsUp } from "lucide-react";
import { cn } from "@/lib/cn";
import { errorMessage, requestJson } from "@/lib/http";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useWorkspace } from "@/components/workspace/workspace-provider";

type Vote = 0 | 1;

/**
 * Avaliação da resposta: o voto vira o score `feedback` do trace no Langfuse
 * (o último voto de cada usuário prevalece) e o link abre o trace da execução
 * no próprio console — prompt enviado, chamadas ao modelo, tools, tokens e custo.
 */
export function MessageFeedback({ runId, className }: { runId: string; className?: string }) {
  const { observability, userId } = useWorkspace();
  const toast = useToast();
  const [vote, setVote] = useState<Vote | null>(null);
  const [sending, setSending] = useState(false);

  if (!observability.enabled) return null;

  async function sendVote(value: Vote) {
    const previous = vote;
    setVote(value);
    setSending(true);
    try {
      await requestJson("/api/observability/scores", {
        method: "POST",
        json: { run_id: runId, name: "feedback", value, user_id: userId },
        fallbackError: "Falha ao registrar o feedback",
      });
    } catch (err) {
      setVote(previous);
      toast({
        title: "Não foi possível registrar o feedback",
        description: errorMessage(err),
        variant: "error",
      });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className={cn("flex items-center", className)} data-voted={vote === null ? undefined : true}>
      {([1, 0] as const).map((value) => {
        const active = vote === value;
        const label = value === 1 ? "Resposta útil" : "Resposta ruim";
        return (
          <Button
            key={value}
            variant="ghost"
            size="icon-xs"
            disabled={sending}
            aria-pressed={active}
            aria-label={label}
            title={label}
            onClick={() => void sendVote(value)}
            className={cn(
              "text-muted-foreground hover:text-foreground",
              active && (value === 1 ? "text-success" : "text-destructive")
            )}
          >
            {value === 1 ? <ThumbsUp /> : <ThumbsDown />}
          </Button>
        );
      })}
      <Link
        href={`/runs/${encodeURIComponent(runId)}`}
        title="Ver o trace desta resposta: spans, tokens, custo e avaliações"
        className="inline-flex h-6 items-center gap-1 rounded-md px-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <Activity className="size-3" />
        Trace
      </Link>
    </div>
  );
}
