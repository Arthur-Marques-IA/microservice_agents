import { proxyJson } from "@/lib/api";

export async function GET(_request: Request, { params }: { params: Promise<{ type: string }> }) {
  const { type } = await params;
  return proxyJson(`/agents/${encodeURIComponent(type)}`);
}

export async function PUT(request: Request, { params }: { params: Promise<{ type: string }> }) {
  const { type } = await params;
  const body = await request.text();
  return proxyJson(`/agents/${encodeURIComponent(type)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ type: string }> }) {
  const { type } = await params;
  return proxyJson(`/agents/${encodeURIComponent(type)}`, { method: "DELETE" });
}
