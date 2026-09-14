"use client";

import { FormEvent, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/admin/status-badge";
import { useContentStatus } from "@/lib/use-content-status";

export function UploadFileForm() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [contentId, setContentId] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { status, statusMessage } = useContentStatus(contentId);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const file = fileInputRef.current?.files?.[0];
    if (!file) return;

    setSubmitting(true);
    setError(null);
    setContentId(null);
    try {
      const formData = new FormData();
      formData.set("file", file);
      const res = await fetch("/api/knowledge/content", { method: "POST", body: formData });
      if (!res.ok) throw new Error(`Falha no upload (HTTP ${res.status})`);
      const data = (await res.json()) as { id: string; name: string };
      setContentId(data.id);
      setFileName(data.name);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro desconhecido");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2">
      <input
        ref={fileInputRef}
        type="file"
        required
        className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-muted file:px-3 file:py-1.5 file:text-sm"
      />
      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={submitting}>
          Enviar arquivo
        </Button>
        {status && <StatusBadge status={status} />}
        {fileName && <span className="text-xs text-muted-foreground">{fileName}</span>}
      </div>
      {statusMessage && <p className="text-xs text-muted-foreground">{statusMessage}</p>}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </form>
  );
}
