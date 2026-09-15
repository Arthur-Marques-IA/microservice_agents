"use client";

import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import type { AgentDefinition, AgentDefinitionInput, MemoryBackend } from "@/lib/types";

const MODEL_OPTIONS = [{ provider: "google", id: "gemini-2.5-flash", label: "Gemini 2.5 Flash" }];

interface AgentFormProps {
  mode: "create" | "edit";
  initial?: AgentDefinition;
  availableTools: string[];
  onSubmit: (input: AgentDefinitionInput) => Promise<void>;
  onCancel: () => void;
}

export function AgentForm({ mode, initial, availableTools, onSubmit, onCancel }: AgentFormProps) {
  const [agentType, setAgentType] = useState(initial?.agent_type ?? "");
  const [name, setName] = useState(initial?.name ?? "");
  const [instructions, setInstructions] = useState((initial?.instructions ?? []).join("\n"));
  const [tools, setTools] = useState<string[]>(initial?.tools ?? []);
  const [modelId, setModelId] = useState(initial?.model_id ?? MODEL_OPTIONS[0].id);
  const [memoryBackend, setMemoryBackend] = useState<MemoryBackend>(initial?.memory_backend ?? "common");
  const [numHistoryRuns, setNumHistoryRuns] = useState(initial?.num_history_runs ?? 10);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleTool(name: string) {
    setTools((prev) => (prev.includes(name) ? prev.filter((t) => t !== name) : [...prev, name]));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const model = MODEL_OPTIONS.find((m) => m.id === modelId);
      await onSubmit({
        agent_type: agentType,
        name,
        instructions: instructions.split("\n").map((l) => l.trim()).filter(Boolean),
        tools,
        model_provider: model?.provider ?? null,
        model_id: model?.id ?? null,
        memory_backend: memoryBackend,
        num_history_runs: numHistoryRuns,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro desconhecido");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">Slug (agent_type)</label>
          <Input
            value={agentType}
            onChange={(e) => setAgentType(e.target.value)}
            placeholder="ex: suporte-nivel-1"
            disabled={mode === "edit"}
            required
            pattern="^[a-z0-9][a-z0-9_-]*$"
            title="letras minúsculas, números, '-' ou '_'"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">Nome</label>
          <Input value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-muted-foreground">
          Instruções (prompt) — uma por linha
        </label>
        <Textarea
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          rows={6}
          required
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">Modelo</label>
          <Select value={modelId} onChange={(e) => setModelId(e.target.value)}>
            {MODEL_OPTIONS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">Memória</label>
          <Select
            value={memoryBackend}
            onChange={(e) => setMemoryBackend(e.target.value as MemoryBackend)}
          >
            <option value="common">Comum (Agno / Postgres)</option>
            <option value="mem0">Mem0</option>
          </Select>
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-muted-foreground">
          Mensagens de histórico consideradas
        </label>
        <Input
          type="number"
          min={0}
          value={numHistoryRuns}
          onChange={(e) => setNumHistoryRuns(Number(e.target.value))}
        />
      </div>

      {availableTools.length > 0 && (
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">Tools</label>
          <div className="flex flex-wrap gap-2">
            {availableTools.map((toolName) => (
              <label key={toolName} className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={tools.includes(toolName)}
                  onChange={() => toggleTool(toolName)}
                />
                {toolName}
              </label>
            ))}
          </div>
        </div>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" disabled={submitting}>
          {mode === "create" ? "Criar agente" : "Salvar alterações"}
        </Button>
      </div>
    </form>
  );
}
