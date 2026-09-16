import { proxyJson } from "@/lib/api";

/** Toolkits padrão do Agno disponíveis para criar uma tool `kind: "builtin"`. */
export async function GET() {
  return proxyJson("/tools/catalog");
}
