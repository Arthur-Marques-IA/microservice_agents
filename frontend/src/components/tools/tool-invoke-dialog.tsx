"use client";

import { useEffect, useState } from "react";
import { Play } from "lucide-react";
import { errorMessage, requestJson } from "@/lib/http";
import { parseDependencies } from "@/lib/agent-meta";
import type { ToolDetail, ToolInvokeResult, ToolSummary } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { CodeBlock } from "@/components/ui/code-block";
import { Dialog, DialogBody, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, Spinner } from "@/components/ui/primitives";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

/** Roda uma tool uma vez, fora de qualquer agente — pra conferir se ela está configurada certo. */
export function ToolInvokeDialog({ tool, onOpenChange }: { tool: ToolSummary; onOpenChange: (open: boolean) => void }) {
  const [detail, setDetail] = useState<ToolDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [functionName, setFunctionName] = useState("");
  const [argumentsText, setArgumentsText] = useState("{}");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ToolInvokeResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    requestJson<ToolDetail>(`/api/tools/${encodeURIComponent(tool.tool_name)}`, { fallbackError: "Falha ao carregar a tool" })
      .then((data) => {
        if (cancelled) return;
        setDetail(data);
        if (data.functions?.length) setFunctionName(data.functions[0]);
      })
      .catch((err) => !cancelled && setLoadError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [tool.tool_name]);

  const argumentsCheck = parseDependencies(argumentsText === "{}" ? "" : argumentsText);

  async function run() {
    if (argumentsCheck.error) return;
    setRunning(true);
    setResult(null);
    try {
      const response = await requestJson<ToolInvokeResult>(`/api/tools/${encodeURIComponent(tool.tool_name)}/invoke`, {
        method: "POST",
        json: {
          arguments: argumentsCheck.value ?? {},
          function_name: tool.kind === "builtin" ? functionName || null : null,
        },
        fallbackError: "Falha ao testar a tool",
      });
      setResult(response);
    } catch (err) {
      setResult({ ok: false, error: errorMessage(err) });
    } finally {
      setRunning(false);
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange} size="md">
      <DialogHeader>
        <DialogTitle>Testar {tool.label}</DialogTitle>
        <DialogDescription>Roda a tool uma vez com os argumentos abaixo, sem passar por um agente.</DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        {loadError && <p className="text-[13px] text-destructive">{loadError}</p>}
        {!detail && !loadError && (
          <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
            <Spinner /> Carregando...
          </p>
        )}
        {detail?.build_error && (
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-[13px] text-destructive">
            {detail.build_error}
          </p>
        )}

        {tool.kind === "builtin" && detail?.functions && (
          <Field label="Função" htmlFor="invoke-function" hint="Uma toolkit padrão tem várias — escolha qual testar.">
            <Select id="invoke-function" value={functionName} onChange={(e) => setFunctionName(e.target.value)}>
              {detail.functions.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </Select>
          </Field>
        )}

        <Field label="Argumentos (JSON)" htmlFor="invoke-args" error={argumentsCheck.error}>
          <Textarea
            id="invoke-args"
            value={argumentsText}
            onChange={(e) => setArgumentsText(e.target.value)}
            rows={5}
            className="font-mono text-xs"
            placeholder='{"a": 1, "b": 2}'
          />
        </Field>

        {result && (
          <div className="flex flex-col gap-2">
            <p className={`text-[13px] font-medium ${result.ok ? "text-success" : "text-destructive"}`}>
              {result.ok ? "Sucesso" : "Erro"}
            </p>
            <CodeBlock
              title={result.ok ? "result" : "error"}
              code={result.ok ? formatResult(result.result) : (result.error ?? "")}
            />
          </div>
        )}
      </DialogBody>
      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          Fechar
        </Button>
        <Button onClick={() => void run()} disabled={running || !detail || Boolean(argumentsCheck.error)}>
          {running ? <Spinner /> : <Play />}
          Rodar
        </Button>
      </DialogFooter>
    </Dialog>
  );
}

function formatResult(result: unknown): string {
  if (typeof result === "string") return result;
  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return String(result);
  }
}
