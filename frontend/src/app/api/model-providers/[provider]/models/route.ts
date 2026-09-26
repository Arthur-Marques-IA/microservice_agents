import { proxyJson } from "@/lib/api";

/** Modelos que o provedor oferece agora, lidos da API dele (cache de 15 min no backend). */
export async function GET(request: Request, { params }: { params: Promise<{ provider: string }> }) {
  const { provider } = await params;
  const { search } = new URL(request.url);
  return proxyJson(`/model-providers/${encodeURIComponent(provider)}/models${search}`);
}
