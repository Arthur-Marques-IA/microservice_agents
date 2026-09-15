import { backendUrl } from "@/lib/api";
import { ChatClient } from "@/components/chat/chat-client";
import type { AgentDefinition } from "@/lib/types";

async function getAgents(): Promise<AgentDefinition[]> {
  try {
    const res = await fetch(backendUrl("/agents"), { cache: "no-store" });
    if (!res.ok) return [];
    const data = (await res.json()) as AgentDefinition[];
    return data;
  } catch {
    return [];
  }
}

export default async function ChatPage() {
  const agents = await getAgents();
  return <ChatClient agents={agents} />;
}
