import { proxyJson } from "@/lib/api";

/** Estado de uma conversa com um agente procedural — o console o usa ao reabrir a conversa. */
export async function GET(_request: Request, { params }: { params: Promise<{ type: string; session: string }> }) {
  const { type, session } = await params;
  return proxyJson(`/agents/${encodeURIComponent(type)}/procedures/${encodeURIComponent(session)}`);
}
