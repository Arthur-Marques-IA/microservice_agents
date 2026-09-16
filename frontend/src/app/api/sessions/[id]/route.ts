import { proxyJson } from "@/lib/api";

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const query = new URLSearchParams();
  const userId = new URL(request.url).searchParams.get("user_id");
  if (userId) query.set("user_id", userId);
  return proxyJson(`/sessions/${encodeURIComponent(id)}?${query}`, { method: "DELETE" });
}
