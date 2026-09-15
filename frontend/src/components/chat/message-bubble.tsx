import { cn } from "@/lib/cn";
import type { ChatMessage } from "@/lib/types";

function UsageBadge({ usage }: { usage: NonNullable<ChatMessage["usage"]> }) {
  const parts = [
    usage.input_tokens != null && `${usage.input_tokens} entrada`,
    usage.output_tokens != null && `${usage.output_tokens} saída`,
  ].filter(Boolean);

  return (
    <p className="mt-1 text-xs text-muted-foreground" title="Total ao final da resposta, não é incremental">
      {usage.total_tokens ?? "?"} tokens{parts.length > 0 ? ` (${parts.join(" / ")})` : ""}
    </p>
  );
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex flex-col", isUser ? "items-end" : "items-start")}>
      <div
        className={cn(
          "max-w-[75%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"
        )}
      >
        {message.content || (
          <span className="inline-flex gap-1 opacity-60">
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.3s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.15s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current" />
          </span>
        )}
      </div>
      {!isUser && message.usage && <UsageBadge usage={message.usage} />}
    </div>
  );
}
