import type { ReactNode } from "react";
import { fetchBackendJson, publicApiUrl } from "@/lib/api";
import type { AgentDefinition, ObservabilityConfig, ToolSummary } from "@/lib/types";
import { AppShell } from "@/components/workspace/app-shell";
import { WorkspaceProvider } from "@/components/workspace/workspace-provider";

/**
 * Layout único do console (playground, agentes e base de conhecimento). Busca
 * no servidor o que todas as áreas compartilham — mutações chamam
 * `router.refresh()` para re-executar este fetch sem recarregar a página.
 */
export default async function WorkspaceLayout({ children }: { children: ReactNode }) {
  const [agents, tools, collections, observability] = await Promise.all([
    fetchBackendJson<AgentDefinition[]>("/agents"),
    fetchBackendJson<ToolSummary[]>("/tools"),
    fetchBackendJson<{ collections: string[] }>("/collections"),
    fetchBackendJson<ObservabilityConfig>("/observability/config"),
  ]);

  return (
    <WorkspaceProvider
      agents={agents ?? []}
      availableTools={tools ?? []}
      collections={collections?.collections ?? []}
      publicApiUrl={publicApiUrl()}
      backendReachable={agents !== null}
      observability={observability ?? { enabled: false, project_url: null }}
    >
      <AppShell>{children}</AppShell>
    </WorkspaceProvider>
  );
}
