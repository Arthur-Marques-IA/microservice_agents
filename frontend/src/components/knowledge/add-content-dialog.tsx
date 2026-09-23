"use client";

import { FormEvent, useId, useState } from "react";
import { FileText, FileUp, Globe, Upload, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { errorMessage, requestJson } from "@/lib/http";
import { formatBytes } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field, Spinner } from "@/components/ui/primitives";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { useWorkspace } from "@/components/workspace/workspace-provider";

type Mode = "text" | "file" | "url";

export function AddContentDialog({
  open,
  onOpenChange,
  collection,
  onAdded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  collection: string;
  onAdded: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="md">
      {open && <AddContentForm collection={collection} onClose={() => onOpenChange(false)} onAdded={onAdded} />}
    </Dialog>
  );
}

function isValidUrl(value: string) {
  try {
    const url = new URL(value.trim());
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function AddContentForm({
  collection,
  onClose,
  onAdded,
}: {
  collection: string;
  onClose: () => void;
  onAdded: () => void;
}) {
  const id = useId();
  const toast = useToast();
  const { collections } = useWorkspace();
  const [mode, setMode] = useState<Mode>("text");
  // Ver o comentário em handleSubmit: o upload do AgentOS não escolhe coleção,
  // então arquivo/URL só valem na que ele alimenta (o backend diz qual é).
  // URL continua presa ao pipeline do AgentOS, que só escreve na coleção padrão.
  // Arquivo não: `POST /collections/{nome}/files` indexa em qualquer coleção,
  // com o embedder dela.
  const urlAllowed = Boolean(collections.find((c) => c.name === collection)?.is_default);
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = mode === "text" ? Boolean(text.trim()) : mode === "file" ? Boolean(file) : isValidUrl(url);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      if (mode === "text") {
        await requestJson(`/api/collections/${encodeURIComponent(collection)}/documents`, {
          method: "POST",
          json: { text, name: name.trim() || undefined },
          fallbackError: "Falha ao enviar o texto",
        });
      } else if (mode === "file" && file) {
        const form = new FormData();
        form.set("file", file);
        if (name.trim()) form.set("name", name.trim());
        await requestJson(`/api/collections/${encodeURIComponent(collection)}/files`, {
          method: "POST",
          body: form,
          fallbackError: "Falha no upload do arquivo",
        });
      } else {
        // URL ainda passa pelo pipeline do AgentOS (`/knowledge/content`), que
        // escreve na coleção padrão — ele não aceita escolher a coleção.
        const form = new FormData();
        form.set("url", url.trim());
        if (name.trim()) form.set("name", name.trim());
        await requestJson("/api/knowledge/content", {
          method: "POST",
          body: form,
          fallbackError: "Falha ao enviar a URL",
        });
      }
      toast({
        title: "Conteúdo enviado",
        description: "A indexação continua em segundo plano — o status aparece na lista.",
        variant: "success",
      });
      onAdded();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col" noValidate>
      <DialogHeader>
        <DialogTitle>Adicionar conteúdo</DialogTitle>
        <DialogDescription>
          Vai para a coleção <span className="font-mono text-foreground">{collection}</span> e é indexado com
          embeddings para busca semântica.
          {!urlAllowed && " URL ainda só funciona na coleção padrão; arquivo e texto valem em qualquer uma."}
        </DialogDescription>
      </DialogHeader>

      <DialogBody className="flex flex-col gap-5">
        <Tabs value={mode} onValueChange={(v) => setMode(v as Mode)} variant="pill">
          <TabsList className={cn("grid w-full", urlAllowed ? "grid-cols-3" : "grid-cols-2")}>
            <TabsTrigger value="text">
              <FileText /> Texto
            </TabsTrigger>
            <TabsTrigger value="file">
              <FileUp /> Arquivo
            </TabsTrigger>
            <TabsTrigger value="url" disabled={!urlAllowed}>
              <Globe /> URL
            </TabsTrigger>
          </TabsList>

          <TabsContent value="text" className="mt-5">
            <Field label="Conteúdo" htmlFor={`${id}-text`}>
              <Textarea
                id={`${id}-text`}
                data-autofocus
                rows={9}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Cole aqui o texto a ser indexado…"
                className="resize-y"
              />
            </Field>
          </TabsContent>

          <TabsContent value="file" className="mt-5 flex flex-col gap-3">
            <label
              htmlFor={`${id}-file`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                const dropped = e.dataTransfer.files?.[0];
                if (dropped) setFile(dropped);
              }}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors",
                dragging ? "border-primary bg-primary-soft/50" : "border-input hover:bg-accent/40"
              )}
            >
              <Upload className="size-6 text-muted-foreground" />
              <span className="text-sm font-medium">
                Arraste um arquivo ou <span className="text-primary">escolha no computador</span>
              </span>
              <span className="text-xs text-muted-foreground">
                Formatos lidos pelos readers do Agno: PDF, DOCX, TXT, CSV, Markdown, JSON…
              </span>
              <input
                id={`${id}-file`}
                type="file"
                className="sr-only"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
            {file && (
              <div className="flex items-center gap-3 rounded-lg border border-border px-3 py-2">
                <FileText className="size-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{file.name}</p>
                  <p className="text-xs text-muted-foreground">{formatBytes(file.size)}</p>
                </div>
                <Button variant="ghost" size="icon-xs" onClick={() => setFile(null)} aria-label="Remover arquivo">
                  <X />
                </Button>
              </div>
            )}
          </TabsContent>

          <TabsContent value="url" className="mt-5">
            <Field
              label="URL"
              htmlFor={`${id}-url`}
              hint="O conteúdo da página é baixado e indexado pelo backend."
              error={url && !isValidUrl(url) ? "Informe uma URL http(s) válida." : null}
            >
              <Input
                id={`${id}-url`}
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://exemplo.com/politica-de-reembolso"
              />
            </Field>
          </TabsContent>
        </Tabs>

        <Field label="Nome (opcional)" htmlFor={`${id}-name`} hint="Ajuda a identificar o documento na lista.">
          <Input
            id={`${id}-name`}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={mode === "file" && file ? file.name : "ex.: política-de-reembolso"}
          />
        </Field>
      </DialogBody>

      <DialogFooter className="items-center">
        {error && <p className="min-w-0 text-[13px] text-destructive sm:mr-auto">{error}</p>}
        <Button variant="outline" onClick={onClose} disabled={submitting}>
          Cancelar
        </Button>
        <Button type="submit" disabled={!canSubmit || submitting}>
          {submitting && <Spinner />} Adicionar
        </Button>
      </DialogFooter>
    </form>
  );
}
