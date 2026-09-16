import { proxyJson } from "@/lib/api";

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyJson(`/knowledge/content/${encodeURIComponent(id)}`, { method: "DELETE" });
}
