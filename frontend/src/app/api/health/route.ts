import { backendUrl } from "@/lib/api";

/** Status do agent-service para o indicador da sidebar. Nunca lança: indisponível vira 503. */
export async function GET() {
  try {
    const res = await fetch(backendUrl("/health"), { cache: "no-store", signal: AbortSignal.timeout(4000) });
    // `environment` é o KURO_ENV_NAME do serviço (ex.: "prod"), quando definido.
    const body = res.ok ? ((await res.json().catch(() => ({}))) as { environment?: string }) : {};
    return Response.json(
      { status: res.ok ? "ok" : "degraded", environment: body.environment ?? null },
      { status: res.ok ? 200 : 503 }
    );
  } catch {
    return Response.json({ status: "unavailable" }, { status: 503 });
  }
}
