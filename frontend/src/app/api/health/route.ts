import { backendUrl } from "@/lib/api";

/** Status do agent-service para o indicador da sidebar. Nunca lança: indisponível vira 503. */
export async function GET() {
  try {
    const res = await fetch(backendUrl("/health"), { cache: "no-store", signal: AbortSignal.timeout(4000) });
    return Response.json({ status: res.ok ? "ok" : "degraded" }, { status: res.ok ? 200 : 503 });
  } catch {
    return Response.json({ status: "unavailable" }, { status: 503 });
  }
}
