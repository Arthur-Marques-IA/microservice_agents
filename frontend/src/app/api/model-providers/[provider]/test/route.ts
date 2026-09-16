import { proxyJson } from "@/lib/api";

/** Testa a chave (salva ou um valor ad-hoc no corpo) chamando um endpoint barato do provedor. */
export async function POST(request: Request, { params }: { params: Promise<{ provider: string }> }) {
  const { provider } = await params;
  return proxyJson(`/model-providers/${encodeURIComponent(provider)}/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}
