import { proxyJson } from "@/lib/api";

/** Lista credenciais (opcionalmente filtradas por `?provider=`). */
export async function GET(request: Request) {
  const { search } = new URL(request.url);
  return proxyJson(`/model-credentials${search}`);
}

export async function POST(request: Request) {
  return proxyJson("/model-credentials", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}
