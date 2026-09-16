import type { Metadata } from "next";
import { RunTraceView } from "@/components/observability/run-trace-view";

export const metadata: Metadata = { title: "Execução" };

/**
 * Trace de uma execução dentro do console. O carregamento é client-side porque
 * um run recém-terminado ainda está sendo indexado — a view tenta de novo sozinha.
 */
export default async function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return <RunTraceView key={runId} runId={runId} />;
}
