import { proxyJson } from "@/lib/api";

/** One-shot de agente `kind: "analysis"` — devolve objeto estruturado, não texto. */
export async function POST(request: Request) {
  const body = await request.text();
  return proxyJson("/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
