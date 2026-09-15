/**
 * Cliente do agent-service, usado SÓ pelos Route Handlers em `app/api/**`
 * (server-side). O browser nunca fala direto com o backend — isso é o que
 * torna o Next.js um BFF aqui: um único hostname/porta pro cliente, sem CORS,
 * e o endereço interno do agent-service nunca vaza pro bundle do browser
 * (por isso a env var não tem prefixo NEXT_PUBLIC_).
 */

const AGENT_SERVICE_URL = process.env.AGENT_SERVICE_URL ?? "http://localhost:8000";

export function backendUrl(path: string): string {
  return `${AGENT_SERVICE_URL}${path}`;
}

const NO_BODY_STATUSES = new Set([204, 205, 304]);

/** Proxy simples: repassa a resposta do backend como está (status, corpo, content-type). */
export async function proxyJson(path: string, init?: RequestInit): Promise<Response> {
  const upstream = await fetch(backendUrl(path), {
    ...init,
    cache: "no-store",
  });
  // Response não aceita corpo (nem "") quando o status é 204/205/304 — ex.
  // o DELETE /agents/{type} do backend responde 204 sem corpo.
  if (NO_BODY_STATUSES.has(upstream.status)) {
    return new Response(null, { status: upstream.status });
  }
  const body = await upstream.text();
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });
}

/** Proxy de streaming: repassa o corpo (ReadableStream) sem bufferizar — essencial pro SSE do chat. */
export async function proxyStream(path: string, init?: RequestInit): Promise<Response> {
  const upstream = await fetch(backendUrl(path), {
    ...init,
    cache: "no-store",
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
