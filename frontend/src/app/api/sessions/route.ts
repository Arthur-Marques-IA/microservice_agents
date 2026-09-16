import { proxyJson } from "@/lib/api";

const FORWARDED_PARAMS = ["user_id", "component_id", "session_name", "limit", "page", "sort_by", "sort_order"];

/**
 * Conversas de um usuário (sessões do AgentOS). Sempre `type=agent` — é o
 * único tipo que este frontend cria — e `user_id` obrigatório, para a
 * sidebar nunca listar conversas de todo mundo.
 */
export async function GET(request: Request) {
  const incoming = new URL(request.url).searchParams;
  if (!incoming.get("user_id")) {
    return Response.json({ detail: "user_id é obrigatório" }, { status: 400 });
  }
  const params = new URLSearchParams({ type: "agent" });
  for (const key of FORWARDED_PARAMS) {
    const value = incoming.get(key);
    if (value) params.set(key, value);
  }
  return proxyJson(`/sessions?${params}`);
}
