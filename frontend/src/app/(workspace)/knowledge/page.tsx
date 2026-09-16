import type { Metadata } from "next";
import { KnowledgeView } from "@/components/knowledge/knowledge-view";

export const metadata: Metadata = { title: "Base de conhecimento" };

export default async function KnowledgePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { add } = await searchParams;
  return <KnowledgeView openAddInitially={add === "1"} />;
}
