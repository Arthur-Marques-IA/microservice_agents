"use client";

import { useEffect, useRef, useState } from "react";
import type { ContentStatus } from "@/lib/types";

/**
 * A ingestão no backend é assíncrona (o AgentOS aceita o conteúdo e processa
 * embeddings em background) — então depois de mandar um documento, a UI
 * precisa ficar checando `/knowledge/content/{id}/status` até sair de
 * "processing", em vez de assumir sucesso assim que o POST volta 201/202.
 */
export function useContentStatus(contentId: string | null) {
  const [status, setStatus] = useState<ContentStatus | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!contentId) return;
    setStatus("processing");

    async function poll() {
      const res = await fetch(`/api/knowledge/content/${contentId}/status`, { cache: "no-store" });
      if (!res.ok) return;
      const data = (await res.json()) as { status: ContentStatus; status_message?: string | null };
      setStatus(data.status);
      setStatusMessage(data.status_message ?? null);
      if (data.status !== "processing" && intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    }

    void poll();
    intervalRef.current = setInterval(poll, 2000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [contentId]);

  return { status, statusMessage };
}
