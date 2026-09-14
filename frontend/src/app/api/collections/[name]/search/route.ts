import { proxyJson } from "@/lib/api";

export async function GET(request: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const search = new URL(request.url).search;
  return proxyJson(`/collections/${encodeURIComponent(name)}/search${search}`);
}
