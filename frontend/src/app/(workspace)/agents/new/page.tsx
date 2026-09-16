import type { Metadata } from "next";
import { AgentCreate } from "@/components/agents/agent-create";

export const metadata: Metadata = { title: "Novo agente" };

export default function NewAgentPage() {
  return <AgentCreate />;
}
