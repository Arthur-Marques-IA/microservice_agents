import { backendUrl } from "@/lib/api";
import { ChatClient } from "@/components/chat/chat-client";

async function getAgentTypes(): Promise<string[]> {
  try {
    const res = await fetch(backendUrl("/agent-types"), { cache: "no-store" });
    if (!res.ok) return ["conversational"];
    const data = (await res.json()) as { agent_types: string[] };
    return data.agent_types.length > 0 ? data.agent_types : ["conversational"];
  } catch {
    return ["conversational"];
  }
}

export default async function ChatPage() {
  const agentTypes = await getAgentTypes();
  return <ChatClient agentTypes={agentTypes} />;
}
