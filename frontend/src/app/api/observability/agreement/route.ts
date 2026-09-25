import { proxyJson } from "@/lib/api";

/** Concordância com a referência (modo shadow) — repassa os filtros como query string. */
export async function GET(request: Request) {
  const { search } = new URL(request.url);
  return proxyJson(`/observability/agreement${search}`);
}
