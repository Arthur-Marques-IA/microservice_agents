import { proxyJson } from "@/lib/api";

/** Sessões recentes agregadas (tokens, custo, feedback) — repassa os filtros como query string. */
export async function GET(request: Request) {
  const { search } = new URL(request.url);
  return proxyJson(`/observability/sessions${search}`);
}
