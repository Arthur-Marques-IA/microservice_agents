import { proxyJson } from "@/lib/api";

/** Execuções de um agente — repassa os filtros (versão, status, cursor...) como query string. */
export async function GET(request: Request, { params }: { params: Promise<{ type: string }> }) {
  const { type } = await params;
  const { search } = new URL(request.url);
  return proxyJson(`/observability/agents/${encodeURIComponent(type)}/runs${search}`);
}
