import { proxyJson } from "@/lib/api";

export async function GET(_request: Request, { params }: { params: Promise<{ type: string }> }) {
  const { type } = await params;
  return proxyJson(`/agents/${encodeURIComponent(type)}/versions`);
}
