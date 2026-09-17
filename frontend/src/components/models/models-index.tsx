"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { CircleCheck, CircleX, Cpu, Settings2 } from "lucide-react";
import { errorMessage, requestJson } from "@/lib/http";
import type { ModelProviderSummary } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, RelativeTime } from "@/components/ui/primitives";
import { useConfirm } from "@/components/ui/confirm";
import { useToast } from "@/components/ui/toast";
import { PageBody, PageHeader } from "@/components/workspace/page-header";
import { useWorkspace } from "@/components/workspace/workspace-provider";
import { ProviderConfigDialog } from "@/components/models/provider-config-dialog";

export function ModelsIndex() {
  const router = useRouter();
  const { modelProviders, backendReachable } = useWorkspace();
  const toast = useToast();
  const confirm = useConfirm();
  const [configuring, setConfiguring] = useState<ModelProviderSummary | null>(null);

  function refresh() {
    router.refresh();
  }

  async function handleRemoveKey(provider: ModelProviderSummary) {
    const confirmed = await confirm({
      title: `Remover a chave de ${provider.label}?`,
      description: "Agentes configurados para este provedor param de funcionar até uma nova chave ser cadastrada.",
      confirmLabel: "Remover chave",
      destructive: true,
    });
    if (!confirmed) return;
    try {
      await requestJson(`/api/model-providers/${encodeURIComponent(provider.provider)}`, {
        method: "DELETE",
        fallbackError: "Falha ao remover",
      });
      toast({ title: "Chave removida", variant: "success" });
      refresh();
    } catch (err) {
      toast({ title: "Não foi possível remover", description: errorMessage(err), variant: "error" });
    }
  }

  return (
    <>
      <PageHeader
        title="Modelos"
        description="Provedores de LLM disponíveis para os agentes — cadastre e teste a chave de cada um aqui."
      />
      <PageBody>
        {!backendReachable ? (
          <Card>
            <EmptyState
              icon={Cpu}
              title="agent-service indisponível"
              description="Não foi possível carregar os provedores. Verifique se o backend está rodando e recarregue a página."
            />
          </Card>
        ) : modelProviders.length === 0 ? (
          <Card>
            <EmptyState
              icon={Cpu}
              title="Nenhum provedor disponível"
              description="O agent-service não retornou provedores de LLM. Verifique a configuração do backend."
            />
          </Card>
        ) : (
          <Card className="divide-y divide-border overflow-hidden">
            {modelProviders.map((provider) => (
              <div key={provider.provider} className="flex items-center gap-3 px-4 py-3">
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-sm font-medium">{provider.label}</span>
                    {provider.configured ? (
                      <Badge variant="success">
                        <CircleCheck /> configurado
                      </Badge>
                    ) : (
                      <Badge variant="secondary">não configurado</Badge>
                    )}
                    {provider.configured && !provider.enabled && <Badge variant="warning">desabilitado</Badge>}
                    {provider.last_test_ok === true && (
                      <Badge variant="success">
                        <CircleCheck /> testado ok
                      </Badge>
                    )}
                    {provider.last_test_ok === false && (
                      <Badge variant="destructive" title={provider.last_test_message ?? undefined}>
                        <CircleX /> falhou no teste
                      </Badge>
                    )}
                  </div>
                  <p className="truncate text-xs text-muted-foreground">
                    {provider.key_hint ? `Chave termina em ${provider.key_hint}` : "Sem chave cadastrada"}
                    {provider.base_url ? ` · ${provider.base_url}` : ""}
                    {provider.last_tested_at && (
                      <>
                        {" "}
                        · testado <RelativeTime date={provider.last_tested_at} />
                      </>
                    )}
                  </p>
                </div>
                <Button variant="outline" size="sm" onClick={() => setConfiguring(provider)}>
                  <Settings2 /> Configurar
                </Button>
                {provider.configured && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => void handleRemoveKey(provider)}
                  >
                    Remover
                  </Button>
                )}
              </div>
            ))}
          </Card>
        )}
      </PageBody>

      {configuring && (
        <ProviderConfigDialog
          provider={configuring}
          onOpenChange={(open) => !open && setConfiguring(null)}
          onSaved={() => {
            setConfiguring(null);
            refresh();
          }}
        />
      )}
    </>
  );
}
