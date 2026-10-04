import { proxyJson } from "@/lib/api";

/** Funil de um agente procedural: quantas conversas estão paradas em cada etapa. */
export async function GET(request: Request, { params }: { params: Promise<{ type: string }> }) {
  const { type } = await params;
  const { search } = new URL(request.url);
  return proxyJson(`/agents/${encodeURIComponent(type)}/procedures${search}`);
}
