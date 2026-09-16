import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { fetchBackendJson } from "@/lib/api";
import type { AgentDefinition, PromptVersion } from "@/lib/types";
import { AgentDetail } from "@/components/agents/agent-detail";

interface Props {
  params: Promise<{ agentType: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

function getAgent(agentType: string) {
  return fetchBackendJson<AgentDefinition>(`/agents/${encodeURIComponent(agentType)}`);
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { agentType } = await params;
  const agent = await getAgent(agentType);
  return { title: agent?.name ?? "Agente" };
}

export default async function AgentPage({ params, searchParams }: Props) {
  const [{ agentType }, { tab }] = await Promise.all([params, searchParams]);
  const [agent, versions] = await Promise.all([
    getAgent(agentType),
    fetchBackendJson<PromptVersion[]>(`/agents/${encodeURIComponent(agentType)}/versions`),
  ]);
  if (!agent) notFound();

  return (
    <AgentDetail
      agent={agent}
      versions={versions ?? []}
      initialTab={typeof tab === "string" ? tab : undefined}
    />
  );
}
