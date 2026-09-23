import { proxyJson } from "@/lib/api";

/** Documentos indexados na coleção, paginados — a tabela da base de conhecimento. */
export async function GET(request: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const incoming = new URL(request.url).searchParams;
  const query = new URLSearchParams();
  for (const key of ["limit", "page"]) {
    const value = incoming.get(key);
    if (value) query.set(key, value);
  }
  return proxyJson(`/collections/${encodeURIComponent(name)}/documents?${query}`);
}

export async function POST(request: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const body = await request.text();
  return proxyJson(`/collections/${encodeURIComponent(name)}/documents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
