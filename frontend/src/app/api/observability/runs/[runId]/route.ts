import { fetchBackendJson } from "@/lib/api";

/**
 * Abre o trace de um run na UI do Langfuse. É um redirect (e não um link
 * direto) porque só o backend sabe o `trace_id` do run e a URL do projeto.
 */
export async function GET(_request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const run = await fetchBackendJson<{ trace_url: string | null }>(
    `/observability/runs/${encodeURIComponent(runId)}`
  );
  if (!run?.trace_url) {
    return new Response("Trace indisponível: o Langfuse não está configurado ou não respondeu.", {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
  return Response.redirect(run.trace_url, 307);
}
