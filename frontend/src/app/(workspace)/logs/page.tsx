import type { Metadata } from "next";
import { LogsView } from "@/components/observability/logs-view";

export const metadata: Metadata = { title: "Logs" };

export default async function LogsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { user_id, session_id } = await searchParams;
  return (
    <LogsView
      userId={typeof user_id === "string" ? user_id : undefined}
      sessionId={typeof session_id === "string" ? session_id : undefined}
    />
  );
}
