import { proxyJson, publicApiUrl } from "@/lib/api";

/**
 * Contrato de integração derivado pelo backend. O console consome isto em vez
 * de montar o próprio exemplo: assim o cURL já vem com o endpoint certo para o
 * tipo do agente, as dependencies que ele declara e o header de autenticação.
 */
export async function GET(request: Request, { params }: { params: Promise<{ type: string }> }) {
  const { type } = await params;
  const baseUrl = new URL(request.url).searchParams.get("base_url") ?? publicApiUrl();
  const query = new URLSearchParams({ base_url: baseUrl });
  return proxyJson(`/agents/${encodeURIComponent(type)}/integration?${query}`);
}
