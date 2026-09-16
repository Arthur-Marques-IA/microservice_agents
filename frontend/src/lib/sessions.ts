import { toDate } from "@/lib/format";
import type { ChatMessage, SessionRun, UsageMetrics } from "@/lib/types";

function asText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function pickUsage(metrics?: UsageMetrics | null): UsageMetrics | undefined {
  if (!metrics) return undefined;
  const { input_tokens, output_tokens, total_tokens, reasoning_tokens, duration } = metrics;
  return { input_tokens, output_tokens, total_tokens, reasoning_tokens, duration };
}

/**
 * Reidrata o histórico de uma sessão a partir dos runs do AgentOS: cada run
 * vira um par pergunta (`run_input`) / resposta (`content`). O `messages[]`
 * do run é ignorado de propósito — ele carrega o system prompt e payloads de
 * tool call, que não são conversa.
 */
export function runsToMessages(runs: SessionRun[]): ChatMessage[] {
  return runs
    .filter((run) => !run.parent_run_id)
    .map((run, order) => ({ run, order, time: run.created_at ? toDate(run.created_at).getTime() : 0 }))
    .sort((a, b) => a.time - b.time || a.order - b.order)
    .flatMap(({ run, time }) => {
      const content = asText(run.content);
      const failed = run.status?.toUpperCase() === "ERROR";
      const messages: ChatMessage[] = [
        { id: `${run.run_id}:user`, role: "user", content: asText(run.run_input), createdAt: time || undefined },
        {
          id: `${run.run_id}:assistant`,
          role: "assistant",
          content,
          usage: pickUsage(run.metrics),
          createdAt: time || undefined,
          runId: run.run_id,
          error: failed && !content ? "A execução falhou no servidor." : undefined,
        },
      ];
      return messages;
    });
}

export function sessionTitle(session: { session_name?: string | null }): string {
  return session.session_name?.trim() || "Conversa sem título";
}
