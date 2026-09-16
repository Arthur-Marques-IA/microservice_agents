import { proxyJson } from "@/lib/api";

/** Execuções de todos os agentes (ou de um só, com `?agent_type=`) — repassa os filtros como query string. */
export async function GET(request: Request) {
  const { search } = new URL(request.url);
  return proxyJson(`/observability/runs${search}`);
}
