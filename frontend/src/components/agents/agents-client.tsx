"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AgentForm } from "@/components/agents/agent-form";
import { PromptHistory } from "@/components/agents/prompt-history";
import type { AgentDefinition, AgentDefinitionInput } from "@/lib/types";

async function fetchAgents(): Promise<AgentDefinition[]> {
  const res = await fetch("/api/agents", { cache: "no-store" });
  if (!res.ok) throw new Error("Falha ao carregar agentes");
  return res.json();
}

export function AgentsClient({
  initialAgents,
  availableTools,
}: {
  initialAgents: AgentDefinition[];
  availableTools: string[];
}) {
  const [agents, setAgents] = useState(initialAgents);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<AgentDefinition | null>(null);

  async function refresh() {
    setAgents(await fetchAgents());
  }

  async function handleCreate(input: AgentDefinitionInput) {
    const res = await fetch("/api/agents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new Error(body?.detail ?? `Falha ao criar agente (HTTP ${res.status})`);
    }
    setCreateOpen(false);
    await refresh();
  }

  async function handleUpdate(input: AgentDefinitionInput) {
    if (!editing) return;
    const res = await fetch(`/api/agents/${editing.agent_type}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new Error(body?.detail ?? `Falha ao salvar agente (HTTP ${res.status})`);
    }
    setEditing(null);
    await refresh();
  }

  async function handleDelete(agentType: string) {
    if (!confirm(`Remover o agente "${agentType}"?`)) return;
    const res = await fetch(`/api/agents/${agentType}`, { method: "DELETE" });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      alert(body?.detail ?? `Falha ao remover agente (HTTP ${res.status})`);
      return;
    }
    await refresh();
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Agentes</h1>
          <p className="text-sm text-muted-foreground">
            Crie e edite agentes sem precisar mexer em código — o prompt é versionado
            automaticamente a cada edição.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" /> Novo agente
        </Button>
      </div>

      <div className="flex flex-col gap-3">
        {agents.map((agent) => (
          <Card key={agent.agent_type}>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <div>
                <CardTitle>{agent.name}</CardTitle>
                <CardDescription>
                  {agent.agent_type} · {agent.model_id ?? "modelo padrão"} · v{agent.prompt_version}
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={agent.memory_backend === "mem0" ? "default" : "muted"}>
                  {agent.memory_backend}
                </Badge>
                {agent.is_seed && <Badge variant="muted">sistema</Badge>}
                <Button size="sm" variant="outline" onClick={() => setEditing(agent)}>
                  Editar
                </Button>
                {!agent.is_seed && (
                  <Button size="sm" variant="ghost" onClick={() => handleDelete(agent.agent_type)}>
                    Remover
                  </Button>
                )}
              </div>
            </CardHeader>
          </Card>
        ))}
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogHeader>
          <DialogTitle>Novo agente</DialogTitle>
          <DialogDescription>Fica disponível em /chat e /chat/stream imediatamente.</DialogDescription>
        </DialogHeader>
        <AgentForm
          mode="create"
          availableTools={availableTools}
          onSubmit={handleCreate}
          onCancel={() => setCreateOpen(false)}
        />
      </Dialog>

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        {editing && (
          <>
            <DialogHeader>
              <DialogTitle>{editing.name}</DialogTitle>
              <DialogDescription>{editing.agent_type}</DialogDescription>
            </DialogHeader>
            <Tabs defaultValue="config">
              <TabsList>
                <TabsTrigger value="config">Configuração</TabsTrigger>
                <TabsTrigger value="history">Histórico de prompts</TabsTrigger>
              </TabsList>
              <TabsContent value="config">
                <AgentForm
                  mode="edit"
                  initial={editing}
                  availableTools={availableTools}
                  onSubmit={handleUpdate}
                  onCancel={() => setEditing(null)}
                />
              </TabsContent>
              <TabsContent value="history">
                <PromptHistory agentType={editing.agent_type} />
              </TabsContent>
            </Tabs>
          </>
        )}
      </Dialog>
    </div>
  );
}
