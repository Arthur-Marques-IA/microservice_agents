import { proxyJson } from "@/lib/api";

/** Testa uma tool sem precisar montar um agente em volta dela. */
export async function POST(request: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  return proxyJson(`/tools/${encodeURIComponent(name)}/invoke`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}
