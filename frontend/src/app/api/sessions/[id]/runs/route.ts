import { proxyJson } from "@/lib/api";

/** Runs de uma sessão — usado para reidratar o histórico da conversa na tela. */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const query = new URLSearchParams({ type: "agent" });
  const userId = new URL(request.url).searchParams.get("user_id");
  if (userId) query.set("user_id", userId);
  return proxyJson(`/sessions/${encodeURIComponent(id)}/runs?${query}`);
}
