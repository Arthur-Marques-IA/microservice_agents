import type { Metadata } from "next";
import { ModelsIndex } from "@/components/models/models-index";

export const metadata: Metadata = { title: "Chaves de API" };

export default function ModelsPage() {
  return <ModelsIndex />;
}
