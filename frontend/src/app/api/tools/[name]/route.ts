import { proxyJson } from "@/lib/api";

export async function GET(_request: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  return proxyJson(`/tools/${encodeURIComponent(name)}`);
}

export async function PUT(request: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  return proxyJson(`/tools/${encodeURIComponent(name)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  return proxyJson(`/tools/${encodeURIComponent(name)}`, { method: "DELETE" });
}
