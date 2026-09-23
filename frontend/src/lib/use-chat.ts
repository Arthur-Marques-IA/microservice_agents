"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { parseSseStream } from "@/lib/sse";
import { readErrorMessage } from "@/lib/http";
import { createId } from "@/lib/id";
import type { Attachment, ChatMessage, UsageMetrics } from "@/lib/types";

interface SendOptions {
  text: string;
  sessionId: string;
  dependencies?: Record<string, unknown> | null;
  /** Imagem, áudio, vídeo ou arquivo — o modelo do agente precisa suportar o tipo. */
  attachments?: Attachment[];
}

/**
 * Estado de uma conversa + streaming via `/api/chat/stream`. O `sessionId`
 * vai por chamada (não no hook) porque uma conversa nova só ganha id no
 * primeiro envio. `send` resolve `true` quando o backend chegou a executar
 * (resposta completa ou parcial) — ou seja, a sessão existe no AgentOS.
 */
export function useChat({
  agentType,
  userId,
  initialMessages,
}: {
  agentType: string;
  userId: string;
  initialMessages?: ChatMessage[];
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages ?? []);
  const [isStreaming, setIsStreaming] = useState(false);
  const streamingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const patchMessage = useCallback((id: string, patch: (message: ChatMessage) => ChatMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? patch(m) : m)));
  }, []);

  const send = useCallback(
    async ({ text, sessionId, dependencies, attachments }: SendOptions): Promise<boolean> => {
      const message = text.trim();
      if ((!message && !attachments?.length) || streamingRef.current) return false;

      streamingRef.current = true;
      setIsStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;

      const assistantId = createId();
      const now = Date.now();
      setMessages((prev) => [
        ...prev,
        { id: createId(), role: "user", content: message, createdAt: now },
        { id: assistantId, role: "assistant", content: "", pending: true, createdAt: now },
      ]);

      let receivedContent = false;
      try {
        const response = await fetch("/api/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            agent_type: agentType,
            user_id: userId,
            session_id: sessionId,
            message,
            dependencies: dependencies ?? undefined,
            attachments: attachments?.length ? attachments : undefined,
          }),
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(await readErrorMessage(response, "Falha ao conversar com o agente"));
        }

        let streamError: string | null = null;
        for await (const sseEvent of parseSseStream(response.body)) {
          if (sseEvent.event === "message") {
            const { content } = JSON.parse(sseEvent.data) as { content?: string };
            if (!content) continue;
            receivedContent = true;
            patchMessage(assistantId, (m) => ({ ...m, content: m.content + content }));
          } else if (sseEvent.event === "usage") {
            const usage = JSON.parse(sseEvent.data) as UsageMetrics;
            patchMessage(assistantId, (m) => ({ ...m, usage }));
          } else if (sseEvent.event === "run") {
            const { run_id } = JSON.parse(sseEvent.data) as { run_id?: string };
            if (run_id) patchMessage(assistantId, (m) => ({ ...m, runId: run_id }));
          } else if (sseEvent.event === "error") {
            const { message: detail } = JSON.parse(sseEvent.data) as { message?: string };
            streamError = detail || "Falha ao executar o agente.";
          }
        }
        const finalError = streamError;
        patchMessage(assistantId, (m) => ({ ...m, pending: false, error: finalError ?? undefined }));
        return true;
      } catch (err) {
        if (controller.signal.aborted) {
          patchMessage(assistantId, (m) => ({ ...m, pending: false, stopped: true }));
          return receivedContent;
        }
        const errorText = err instanceof Error ? err.message : "Erro desconhecido";
        patchMessage(assistantId, (m) => ({ ...m, pending: false, error: errorText }));
        return receivedContent;
      } finally {
        streamingRef.current = false;
        abortRef.current = null;
        setIsStreaming(false);
      }
    },
    [agentType, userId, patchMessage]
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  /** Remove a mensagem `id` e tudo depois dela (usado no "tentar novamente"). */
  const truncateFrom = useCallback((id: string) => {
    setMessages((prev) => {
      const index = prev.findIndex((m) => m.id === id);
      return index === -1 ? prev : prev.slice(0, index);
    });
  }, []);

  return { messages, send, stop, truncateFrom, isStreaming };
}
