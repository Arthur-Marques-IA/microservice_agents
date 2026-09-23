import { CircleAlert, RotateCcw } from "lucide-react";
import { formatDuration, formatNumber } from "@/lib/format";
import type { ChatMessage } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { AgentAvatar } from "@/components/agents/agent-avatar";
import { MessageContent } from "@/components/chat/message-content";
import { MessageFeedback } from "@/components/chat/message-feedback";

function TypingIndicator() {
  return (
    <span className="inline-flex h-6 items-center gap-1 text-muted-foreground" aria-label="Gerando resposta">
      <span className="size-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.3s]" />
      <span className="size-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.15s]" />
      <span className="size-1.5 animate-bounce rounded-full bg-current" />
    </span>
  );
}

function UsageSummary({ usage }: { usage: NonNullable<ChatMessage["usage"]> }) {
  const breakdown = [
    usage.input_tokens != null && `${formatNumber(usage.input_tokens)} entrada`,
    usage.output_tokens != null && `${formatNumber(usage.output_tokens)} saída`,
    usage.reasoning_tokens ? `${formatNumber(usage.reasoning_tokens)} raciocínio` : null,
  ].filter(Boolean);

  return (
    <span
      className="text-xs tabular-nums text-muted-foreground"
      title={`Total ao final da resposta${breakdown.length ? `: ${breakdown.join(" · ")}` : ""}`}
    >
      {usage.total_tokens != null ? `${formatNumber(usage.total_tokens)} tokens` : "tokens: ?"}
      {typeof usage.duration === "number" && ` · ${formatDuration(usage.duration)}`}
    </span>
  );
}

export function MessageBubble({
  message,
  agentType,
  agentName,
  sessionId,
  onRetry,
}: {
  message: ChatMessage;
  agentType: string;
  agentName?: string;
  /** Necessário para ensinar o agente a partir desta conversa. */
  sessionId?: string | null;
  onRetry?: () => void;
}) {
  if (message.role === "user") {
    return (
      <div className="group flex flex-col items-end gap-1">
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-muted px-4 py-2.5 text-sm leading-relaxed">
          {message.content}
        </div>
        <div className="flex h-6 items-center opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100">
          <CopyButton value={message.content} label="Copiar mensagem" />
        </div>
      </div>
    );
  }

  const showFooter =
    !message.pending && (Boolean(message.content) || Boolean(message.usage) || Boolean(message.runId));

  return (
    <div className="group flex gap-3">
      <AgentAvatar agentType={agentType} name={agentName} size="sm" className="mt-0.5" />
      <div className="min-w-0 flex-1">
        <p className="mb-1 text-[13px] font-medium">{agentName ?? agentType}</p>

        {message.pending && !message.content ? <TypingIndicator /> : message.content ? <MessageContent content={message.content} /> : null}

        {message.stopped && <p className="mt-1.5 text-xs text-muted-foreground">Resposta interrompida.</p>}

        {message.error && (
          <div className="mt-2 flex flex-wrap items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-[13px]">
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" />
            <div className="min-w-0 flex-1">
              <p className="font-medium text-destructive">Não foi possível gerar a resposta</p>
              <p className="break-words text-muted-foreground">{message.error}</p>
            </div>
            {onRetry && (
              <Button size="sm" variant="outline" onClick={onRetry}>
                <RotateCcw /> Tentar novamente
              </Button>
            )}
          </div>
        )}

        {showFooter && (
          <div className="mt-1.5 flex h-6 items-center gap-1.5">
            {message.usage && <UsageSummary usage={message.usage} />}
            {/* Ações aparecem no hover — menos o voto já dado, que fica visível. */}
            <div className="flex items-center opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100 has-[[data-voted]]:opacity-100 [@media(hover:none)]:opacity-100">
              {message.content && <CopyButton value={message.content} label="Copiar resposta" />}
              {message.runId && (
                <MessageFeedback runId={message.runId} agentType={agentType} sessionId={sessionId ?? null} />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
