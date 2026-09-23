"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { FileSearch, Paperclip, Play, X } from "lucide-react";
import { errorMessage, requestJson } from "@/lib/http";
import type { AnalyzeResponse, Attachment } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CodeBlock } from "@/components/ui/code-block";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, Field, SectionHeading, Spinner } from "@/components/ui/primitives";
import { PageBody, PageHeader } from "@/components/workspace/page-header";
import { useWorkspace } from "@/components/workspace/workspace-provider";
import { readAttachment } from "@/lib/attachments";

/**
 * Onde se testa um agente `kind: "analysis"`. Ele não aparece no Playground
 * porque não conversa: é uma chamada só, com um documento de entrada e um
 * objeto de saída no formato do `response_schema`.
 */
export function AnalyzeView() {
  const { agents } = useWorkspace();
  const analistas = useMemo(() => agents.filter((a) => a.kind === "analysis"), [agents]);

  const [agentType, setAgentType] = useState("");
  const [document, setDocument] = useState("");
  const [deps, setDeps] = useState("");
  const [anexos, setAnexos] = useState<{ attachment: Attachment; name: string }[]>([]);
  const [rodando, setRodando] = useState(false);
  const [resultado, setResultado] = useState<AnalyzeResponse | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const escolhido = analistas.find((a) => a.agent_type === agentType) ?? analistas[0];

  async function rodar() {
    if (!escolhido) return;
    setRodando(true);
    setErro(null);
    setResultado(null);
    try {
      let dependencies: Record<string, unknown> | undefined;
      if (deps.trim()) {
        try {
          dependencies = JSON.parse(deps) as Record<string, unknown>;
        } catch {
          throw new Error("As dependencies precisam ser um objeto JSON válido.");
        }
      }
      setResultado(
        await requestJson<AnalyzeResponse>("/api/analyze", {
          method: "POST",
          json: {
            agent_type: escolhido.agent_type,
            document,
            dependencies,
            attachments: anexos.map((a) => a.attachment),
          },
          fallbackError: "Falha ao analisar",
        })
      );
    } catch (err) {
      setErro(errorMessage(err));
    } finally {
      setRodando(false);
    }
  }

  async function anexar(files: FileList | null) {
    if (!files) return;
    for (const file of Array.from(files)) {
      try {
        const attachment = await readAttachment(file);
        setAnexos((prev) => [...prev, { attachment, name: file.name }]);
      } catch (err) {
        setErro(errorMessage(err));
      }
    }
  }

  if (analistas.length === 0) {
    return (
      <>
        <PageHeader title="Análise" description="Agentes analistas: um documento entra, um objeto estruturado sai." />
        <PageBody>
          <Card>
            <EmptyState
              icon={FileSearch}
              title="Nenhum agente analista ainda"
              description="Um agente do tipo Analista recebe um texto e devolve os campos do response_schema — sem sessão e sem histórico."
              action={
                <Link href="/agents/new" className={buttonVariants({ variant: "outline", size: "sm" })}>
                  Criar agente
                </Link>
              }
            />
          </Card>
        </PageBody>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Análise" description="Agentes analistas: um documento entra, um objeto estruturado sai." />
      <PageBody className="flex flex-col gap-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Agente" htmlFor="analyze-agent">
            <Select id="analyze-agent" value={escolhido?.agent_type ?? ""} onChange={(e) => setAgentType(e.target.value)}>
              {analistas.map((a) => (
                <option key={a.agent_type} value={a.agent_type}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Dependencies (JSON)"
            htmlFor="analyze-deps"
            hint="Opcional — os mesmos campos que o /analyze aceita."
          >
            <Input
              id="analyze-deps"
              value={deps}
              onChange={(e) => setDeps(e.target.value)}
              placeholder='{"cliente_id": 42}'
              className="font-mono text-xs"
            />
          </Field>
        </div>

        <Field
          label="Documento"
          htmlFor="analyze-document"
          hint="Texto puro ou JSON — o histórico de uma conversa, um contrato, um atendimento."
        >
          <Textarea
            id="analyze-document"
            value={document}
            onChange={(e) => setDocument(e.target.value)}
            rows={10}
            className="min-h-40 resize-y font-mono text-[13px]"
            placeholder="Cole aqui o texto a analisar."
          />
        </Field>

        <div className="flex flex-wrap items-center gap-2">
          <label className={buttonVariants({ variant: "outline", size: "sm" })}>
            <Paperclip /> Anexar
            <input type="file" multiple className="hidden" onChange={(e) => void anexar(e.target.files)} />
          </label>
          {anexos.map((a, i) => (
            <Badge key={i} variant="secondary" className="gap-1">
              {a.name}
              <button
                type="button"
                aria-label={`Remover ${a.name}`}
                onClick={() => setAnexos((prev) => prev.filter((_, idx) => idx !== i))}
              >
                <X className="size-3" />
              </button>
            </Badge>
          ))}
          <div className="flex-1" />
          <Button onClick={() => void rodar()} disabled={rodando || (!document.trim() && anexos.length === 0)}>
            {rodando ? <Spinner /> : <Play />} Analisar
          </Button>
        </div>

        {erro && <p className="text-[13px] text-destructive">{erro}</p>}

        {resultado && (
          <div className="flex flex-col gap-3">
            <SectionHeading
              title="Resultado"
              description={`run ${resultado.run_id} — validado contra o response_schema do agente.`}
            />
            <CodeBlock code={JSON.stringify(resultado.result, null, 2)} title="result" />
          </div>
        )}

        {escolhido && (
          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Campos que este agente devolve</h3>
            <CodeBlock code={JSON.stringify(escolhido.response_schema, null, 2)} title="response_schema" />
          </div>
        )}
      </PageBody>
    </>
  );
}
