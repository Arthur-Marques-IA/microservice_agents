import { proxyJson } from "@/lib/api";

/** Versões da configuração inteira do agente — a atual vem com `current: true`. */
export async function GET(_request: Request, { params }: { params: Promise<{ type: string }> }) {
  const { type } = await params;
  return proxyJson(`/agents/${encodeURIComponent(type)}/revisions`);
}
