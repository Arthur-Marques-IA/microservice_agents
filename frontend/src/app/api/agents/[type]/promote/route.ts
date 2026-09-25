import { proxyJson } from "@/lib/api";

/** Copia a configuração deste agente para `to` (draft → prod, ou prod → draft). */
export async function POST(request: Request, { params }: { params: Promise<{ type: string }> }) {
  const { type } = await params;
  return proxyJson(`/agents/${encodeURIComponent(type)}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}
