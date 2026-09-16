import { proxyJson } from "@/lib/api";

/** Série diária + contagem por status, para os gráficos dos Logs — repassa os filtros como query string. */
export async function GET(request: Request) {
  const { search } = new URL(request.url);
  return proxyJson(`/observability/stats${search}`);
}
