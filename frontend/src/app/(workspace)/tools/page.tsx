import type { Metadata } from "next";
import { ToolsIndex } from "@/components/tools/tools-index";

export const metadata: Metadata = { title: "Tools" };

export default function ToolsPage() {
  return <ToolsIndex />;
}
