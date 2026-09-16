import type { Metadata } from "next";
import { ChatView } from "@/components/chat/chat-view";

export const metadata: Metadata = { title: "Playground" };

export default async function NewChatPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { agent } = await searchParams;
  return <ChatView sessionId={null} requestedAgent={typeof agent === "string" ? agent : undefined} />;
}
