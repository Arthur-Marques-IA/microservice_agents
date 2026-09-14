import { proxyJson } from "@/lib/api";

export async function POST(request: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const body = await request.text();
  return proxyJson(`/collections/${encodeURIComponent(name)}/documents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
