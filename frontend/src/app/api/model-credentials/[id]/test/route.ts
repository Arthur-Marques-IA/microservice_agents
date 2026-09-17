import { proxyJson } from "@/lib/api";

/** Testa a chave salva (ou um valor ad-hoc no corpo) chamando um endpoint barato do provedor. */
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyJson(`/model-credentials/${encodeURIComponent(id)}/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}
