import { backendUrl } from "@/lib/api";

/**
 * Proxy pro upload de arquivo do AgentOS (`POST /knowledge/content`,
 * multipart). Diferente dos outros proxies, aqui a gente lê o FormData
 * (buffeiriza em memória) e remonta — repassar o body cru de um multipart
 * sem reescrever o boundary/Content-Length é mais frágil do que vale a pena
 * para um painel admin de upload avulso. Para arquivos grandes, prefira
 * ingestão por texto/URL ou aumente esse limite com cuidado.
 */
export async function POST(request: Request) {
  const formData = await request.formData();
  const upstream = await fetch(backendUrl("/knowledge/content"), {
    method: "POST",
    body: formData,
    cache: "no-store",
  });
  const body = await upstream.text();
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });
}
