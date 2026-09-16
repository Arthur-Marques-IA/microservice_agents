import type { Metadata } from "next";
import { AgentsIndex } from "@/components/agents/agents-index";

export const metadata: Metadata = { title: "Agentes" };

export default function AgentsPage() {
  return <AgentsIndex />;
}
