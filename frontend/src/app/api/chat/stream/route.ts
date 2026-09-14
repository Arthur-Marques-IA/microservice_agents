import { proxyStream } from "@/lib/api";

/**
 * Proxy de streaming (SSE) pro `/chat/stream` do agent-service. POST, não
 * GET: a mensagem do usuário vai no corpo, e o cliente não usa `EventSource`
 * (que só faz GET) — usa `fetch` + leitura manual do `ReadableStream`
 * (ver `useChatStream` no client).
 */
export async function POST(request: Request) {
  const body = await request.text();
  return proxyStream("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
