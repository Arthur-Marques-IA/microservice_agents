import type { Metadata } from "next";
import { ObservabilityView } from "@/components/observability/observability-view";

export const metadata: Metadata = { title: "Observabilidade" };

export default async function ObservabilityPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { user_id, session_id } = await searchParams;
  return (
    <ObservabilityView
      userId={typeof user_id === "string" ? user_id : undefined}
      sessionId={typeof session_id === "string" ? session_id : undefined}
    />
  );
}
