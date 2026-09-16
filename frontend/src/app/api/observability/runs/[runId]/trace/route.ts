import { proxyJson } from "@/lib/api";

/** Trace completo de um run (spans, tokens, custo, scores), lido do Langfuse pelo backend. */
export async function GET(_request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return proxyJson(`/observability/runs/${encodeURIComponent(runId)}/trace`);
}
