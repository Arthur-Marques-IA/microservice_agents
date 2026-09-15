import { backendUrl } from "@/lib/api";
import { AgentsClient } from "@/components/agents/agents-client";
import type { AgentDefinition } from "@/lib/types";

async function getAgents(): Promise<AgentDefinition[]> {
  const res = await fetch(backendUrl("/agents"), { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

async function getAvailableTools(): Promise<string[]> {
  const res = await fetch(backendUrl("/tools"), { cache: "no-store" });
  if (!res.ok) return [];
  const data = (await res.json()) as { tools: string[] };
  return data.tools;
}

export default async function AgentsPage() {
  const [agents, availableTools] = await Promise.all([getAgents(), getAvailableTools()]);
  return <AgentsClient initialAgents={agents} availableTools={availableTools} />;
}
