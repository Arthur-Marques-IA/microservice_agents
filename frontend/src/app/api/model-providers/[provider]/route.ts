import { proxyJson } from "@/lib/api";

export async function GET(_request: Request, { params }: { params: Promise<{ provider: string }> }) {
  const { provider } = await params;
  return proxyJson(`/model-providers/${encodeURIComponent(provider)}`);
}

export async function PUT(request: Request, { params }: { params: Promise<{ provider: string }> }) {
  const { provider } = await params;
  return proxyJson(`/model-providers/${encodeURIComponent(provider)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ provider: string }> }) {
  const { provider } = await params;
  return proxyJson(`/model-providers/${encodeURIComponent(provider)}`, { method: "DELETE" });
}
