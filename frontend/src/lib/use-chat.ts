"use client";

import { useCallback, useState } from "react";
import { parseSseStream } from "@/lib/sse";
import type { ChatMessage, UsageMetrics } from "@/lib/types";

function newId(): string {
  return crypto.randomUUID();
}

export function useChat(params: { agentType: string; userId: string; sessionId: string }) {
  const { agentType, userId, sessionId } = params;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (text: string, dependencies?: Record<string, unknown>) => {
      if (!text.trim() || isStreaming) return;

      setError(null);
      const userMessage: ChatMessage = { id: newId(), role: "user", content: text };
      const assistantId = newId();
      setMessages((prev) => [...prev, userMessage, { id: assistantId, role: "assistant", content: "" }]);
      setIsStreaming(true);

      try {
        const response = await fetch("/api/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            agent_type: agentType,
            user_id: userId,
            session_id: sessionId,
            message: text,
            dependencies,
          }),
        });

        if (!response.ok || !response.body) {
          throw new Error(`Falha ao conversar com o agente (HTTP ${response.status})`);
        }

        for await (const sseEvent of parseSseStream(response.body)) {
          if (sseEvent.event === "message") {
            const parsed = JSON.parse(sseEvent.data) as { content?: string };
            if (!parsed.content) continue;
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + parsed.content } : m))
            );
          } else if (sseEvent.event === "usage") {
            const usage = JSON.parse(sseEvent.data) as UsageMetrics;
            setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, usage } : m)));
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Erro desconhecido");
      } finally {
        setIsStreaming(false);
      }
    },
    [agentType, userId, sessionId, isStreaming]
  );

  return { messages, sendMessage, isStreaming, error };
}
