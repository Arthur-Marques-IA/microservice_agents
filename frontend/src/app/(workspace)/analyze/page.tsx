import type { Metadata } from "next";
import { AnalyzeView } from "@/components/analyze/analyze-view";

export const metadata: Metadata = { title: "Análise" };

export default function AnalyzePage() {
  return <AnalyzeView />;
}
