import { proxyJson } from "@/lib/api";

/** Registra uma avaliação de trace (ex.: 👍/👎 numa resposta do playground). */
export async function POST(request: Request) {
  return proxyJson("/observability/scores", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}
