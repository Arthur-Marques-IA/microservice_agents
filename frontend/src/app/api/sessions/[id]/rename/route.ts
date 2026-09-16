import { proxyJson } from "@/lib/api";

/** Corpo: `{"session_name": "..."}` (o AgentOS usa `Body(embed=True)`). */
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const query = new URLSearchParams({ type: "agent" });
  const userId = new URL(request.url).searchParams.get("user_id");
  if (userId) query.set("user_id", userId);
  const body = await request.text();
  return proxyJson(`/sessions/${encodeURIComponent(id)}/rename?${query}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
