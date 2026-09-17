import { proxyJson } from "@/lib/api";

/** Testa provider+api_key antes de salvar — usado no diálogo de nova chave. */
export async function POST(request: Request) {
  return proxyJson("/model-credentials/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}
