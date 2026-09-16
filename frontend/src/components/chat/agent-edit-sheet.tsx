"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ExternalLink } from "lucide-react";
import { requestJson } from "@/lib/http";
import type { AgentDefinition } from "@/lib/types";
import { Dialog, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { AgentForm, type AgentFormPayload } from "@/components/agents/agent-form";
import { useWorkspace } from "@/components/workspace/workspace-provider";

/** Edita o agente num painel lateral, sem sair da conversa. */
export function AgentEditSheet({
  open,
  onOpenChange,
  agent,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agent: AgentDefinition;
}) {
  const router = useRouter();
  const toast = useToast();
  const { availableTools } = useWorkspace();
  const slug = encodeURIComponent(agent.agent_type);

  async function handleSave(payload: AgentFormPayload) {
    const updated = await requestJson<AgentDefinition>(`/api/agents/${slug}`, {
      method: "PUT",
      json: payload,
      fallbackError: "Falha ao salvar agente",
    });
    toast({
      title: "Agente atualizado",
      description: payload.instructions
        ? `Prompt v${updated.prompt_version} já vale para a próxima mensagem.`
        : "As alterações já valem para a próxima mensagem.",
      variant: "success",
    });
    onOpenChange(false);
    router.refresh();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange} side="right" className="sm:max-w-xl">
      <DialogHeader className="border-b border-border">
        <DialogTitle>Editar {agent.name}</DialogTitle>
        <DialogDescription className="flex flex-wrap items-center gap-x-2">
          As mudanças valem para as próximas mensagens desta conversa.
          <Link
            href={`/agents/${slug}`}
            onClick={() => onOpenChange(false)}
            className="inline-flex items-center gap-1 text-primary hover:underline"
          >
            Abrir página do agente <ExternalLink className="size-3" />
          </Link>
        </DialogDescription>
      </DialogHeader>
      {open && (
        <AgentForm
          key={agent.updated_at}
          mode="edit"
          variant="sheet"
          agent={agent}
          availableTools={availableTools}
          onSubmit={handleSave}
          onCancel={() => onOpenChange(false)}
        />
      )}
    </Dialog>
  );
}
