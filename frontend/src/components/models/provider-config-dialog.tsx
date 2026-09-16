"use client";

import { useState } from "react";
import { CircleCheck, CircleX, ExternalLink } from "lucide-react";
import { errorMessage, requestJson } from "@/lib/http";
import type { ModelProviderSummary, ModelProviderTestResult, ModelProviderUpdateInput } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, Spinner } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";

export function ProviderConfigDialog({
  provider,
  onOpenChange,
  onSaved,
}: {
  provider: ModelProviderSummary;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(provider.base_url ?? "");
  const [enabled, setEnabled] = useState(provider.enabled);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ModelProviderTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canTest = provider.requires_api_key ? Boolean(apiKey || provider.configured) : true;

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    setError(null);
    try {
      const result = await requestJson<ModelProviderTestResult>(
        `/api/model-providers/${encodeURIComponent(provider.provider)}/test`,
        {
          method: "POST",
          json: {
            ...(apiKey ? { api_key: apiKey } : {}),
            ...(provider.supports_custom_base_url && baseUrl ? { base_url: baseUrl } : {}),
          },
          fallbackError: "Falha ao testar",
        }
      );
      setTestResult(result);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const body: ModelProviderUpdateInput = { enabled };
      if (apiKey) body.api_key = apiKey;
      if (provider.supports_custom_base_url) body.base_url = baseUrl;
      await requestJson(`/api/model-providers/${encodeURIComponent(provider.provider)}`, {
        method: "PUT",
        json: body,
        fallbackError: "Falha ao salvar",
      });
      toast({ title: `${provider.label} salvo`, variant: "success" });
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange} size="sm">
      <DialogHeader>
        <DialogTitle>{provider.label}</DialogTitle>
        <DialogDescription>
          {provider.requires_api_key
            ? "A chave é cifrada em repouso e nunca volta numa resposta da API."
            : "Não exige chave — só o endereço do servidor."}{" "}
          <a
            href={provider.docs_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-0.5 text-primary hover:underline"
          >
            Onde conseguir <ExternalLink className="size-3" />
          </a>
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        {provider.requires_api_key && (
          <Field
            label="Chave de API"
            htmlFor="provider-api-key"
            hint={provider.configured ? `Chave salva termina em ${provider.key_hint}. Deixe em branco para manter.` : undefined}
          >
            <Input
              id="provider-api-key"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={provider.configured ? "••••••••••••" : "sk-..."}
              data-autofocus
            />
          </Field>
        )}
        {provider.supports_custom_base_url && (
          <Field label="Endereço customizado" htmlFor="provider-base-url" hint="Opcional — para um endpoint próprio ou self-hosted.">
            <Input
              id="provider-base-url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={provider.provider === "ollama" ? "http://localhost:11434" : "https://..."}
            />
          </Field>
        )}
        <label className="flex w-fit cursor-pointer items-center gap-2 text-[13px]">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} className="accent-primary" />
          Habilitado (disponível para os agentes escolherem)
        </label>

        <div className="flex items-center gap-2 border-t border-border pt-4">
          <Button type="button" variant="outline" size="sm" onClick={() => void handleTest()} disabled={testing || !canTest}>
            {testing && <Spinner />}
            Testar
          </Button>
          {testResult && (
            <span className={`inline-flex items-center gap-1 text-xs ${testResult.ok ? "text-success" : "text-destructive"}`}>
              {testResult.ok ? <CircleCheck className="size-3.5" /> : <CircleX className="size-3.5" />}
              {testResult.ok ? "Chave válida" : testResult.message}
            </span>
          )}
        </div>
        {error && (
          <Badge variant="destructive" className="h-auto w-fit whitespace-normal px-2 py-1 text-left">
            {error}
          </Badge>
        )}
      </DialogBody>
      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          Cancelar
        </Button>
        <Button onClick={() => void handleSave()} disabled={saving}>
          {saving && <Spinner />}
          Salvar
        </Button>
      </DialogFooter>
    </Dialog>
  );
}
