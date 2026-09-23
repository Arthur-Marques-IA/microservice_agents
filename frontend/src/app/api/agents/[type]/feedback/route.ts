import { proxyJson } from "@/lib/api";

const base = (type: string) => `/agents/${encodeURIComponent(type)}/feedback`;

/** Regras de comportamento do agente. 404 enquanto não houver nenhuma. */
export async function GET(_request: Request, { params }: { params: Promise<{ type: string }> }) {
  const { type } = await params;
  return proxyJson(base(type));
}

/** Mescla um feedback textual sobre uma conversa; a resposta traz o `diff`. */
export async function POST(request: Request, { params }: { params: Promise<{ type: string }> }) {
  const { type } = await params;
  const body = await request.text();
  return proxyJson(base(type), { method: "POST", headers: { "Content-Type": "application/json" }, body });
}

/** Substitui as regras à mão, sem passar pelo modelo. */
export async function PUT(request: Request, { params }: { params: Promise<{ type: string }> }) {
  const { type } = await params;
  const body = await request.text();
  return proxyJson(base(type), { method: "PUT", headers: { "Content-Type": "application/json" }, body });
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ type: string }> }) {
  const { type } = await params;
  return proxyJson(base(type), { method: "DELETE" });
}
