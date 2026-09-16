import type { Metadata } from "next";
import { SessionDetailView } from "@/components/observability/session-detail-view";

export const metadata: Metadata = { title: "Sessão" };

export default async function LogsSessionPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return <SessionDetailView sessionId={sessionId} />;
}
