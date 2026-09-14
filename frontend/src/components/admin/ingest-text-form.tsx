"use client";

import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { StatusBadge } from "@/components/admin/status-badge";
import { useContentStatus } from "@/lib/use-content-status";

export function IngestTextForm({ collection }: { collection: string }) {
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [contentId, setContentId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { status, statusMessage } = useContentStatus(contentId);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setContentId(null);
    try {
      const res = await fetch(`/api/collections/${collection}/documents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, name: name || undefined }),
      });
      if (!res.ok) throw new Error(`Falha ao enviar texto (HTTP ${res.status})`);
      const data = (await res.json()) as { content_id: string };
      setContentId(data.content_id);
      setText("");
      setName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro desconhecido");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2">
      <Input placeholder="Nome (opcional)" value={name} onChange={(e) => setName(e.target.value)} />
      <Textarea
        placeholder="Cole o texto a ser indexado..."
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
        required
      />
      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={submitting || !text.trim()}>
          Ingerir texto
        </Button>
        {status && <StatusBadge status={status} />}
      </div>
      {statusMessage && <p className="text-xs text-muted-foreground">{statusMessage}</p>}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </form>
  );
}
