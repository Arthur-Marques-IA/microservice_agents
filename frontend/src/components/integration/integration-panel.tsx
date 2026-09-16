"use client";

import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { buildSnippet, SNIPPET_LANGUAGES, type ChatEndpoint, type SnippetLanguage } from "@/lib/snippets";
import { useLocalStorage } from "@/lib/use-local-storage";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { CodeBlock } from "@/components/ui/code-block";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWorkspace } from "@/components/workspace/workspace-provider";

const EXAMPLE_DEPENDENCIES = { cpf: "000.000.000-00", nome: "Maria", plano: "premium" };

/**
 * Exemplo de chamada ao contrato estável (`/chat`, `/chat/stream`) — no
 * agente, pré-preenchido com o slug; no chat, com a sessão e o contexto reais.
 */
export function IntegrationPanel({
  agentType,
  userId = "user-123",
  sessionId = "session-abc",
  dependencies,
  showReference = false,
}: {
  agentType: string;
  userId?: string;
  sessionId?: string;
  dependencies?: Record<string, unknown> | null;
  showReference?: boolean;
}) {
  const { publicApiUrl } = useWorkspace();
  const hasRealDependencies = Boolean(dependencies && Object.keys(dependencies).length > 0);
  const [endpoint, setEndpoint] = useState<ChatEndpoint>("/chat/stream");
  const [language, setLanguage] = useLocalStorage<SnippetLanguage>("agent-service:snippet-language", "curl");
  const [includeDependencies, setIncludeDependencies] = useState(hasRealDependencies);
  const [baseUrl, setBaseUrl] = useState(publicApiUrl);

  const code = buildSnippet(language, {
    baseUrl: baseUrl.replace(/\/+$/, ""),
    endpoint,
    agentType,
    userId,
    sessionId,
    message: "Olá! Como você pode me ajudar?",
    dependencies: includeDependencies ? (hasRealDependencies ? dependencies : EXAMPLE_DEPENDENCIES) : null,
  });
  const languageLabel = SNIPPET_LANGUAGES.find((l) => l.value === language)?.label ?? language;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Tabs value={endpoint} onValueChange={(v) => setEndpoint(v as ChatEndpoint)} variant="pill">
            <TabsList>
              <TabsTrigger value="/chat/stream">Streaming (SSE)</TabsTrigger>
              <TabsTrigger value="/chat">Resposta única</TabsTrigger>
            </TabsList>
          </Tabs>
          <Tabs value={language} onValueChange={(v) => setLanguage(v as SnippetLanguage)} variant="pill">
            <TabsList>
              {SNIPPET_LANGUAGES.map((l) => (
                <TabsTrigger key={l.value} value={l.value}>
                  {l.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <label className="flex min-w-0 flex-1 items-center gap-2 text-[13px]">
            <span className="shrink-0 text-muted-foreground">Base URL</span>
            <Input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="h-8 max-w-xs font-mono text-xs"
              spellCheck={false}
            />
          </label>
          <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
            <input
              type="checkbox"
              checked={includeDependencies}
              onChange={(e) => setIncludeDependencies(e.target.checked)}
              className="accent-primary"
            />
            Incluir <code className="font-mono text-xs text-foreground">dependencies</code>
            {!hasRealDependencies && " (exemplo)"}
          </label>
        </div>
        <CodeBlock code={code} title={`POST ${endpoint} · ${languageLabel}`} />
      </div>

      {showReference && <ApiReference baseUrl={baseUrl.replace(/\/+$/, "")} />}
    </div>
  );
}

const PARAMETERS = [
  {
    name: "user_id",
    type: "string",
    required: true,
    description: "Identificador estável do usuário final na sua plataforma — base das memórias de longo prazo.",
  },
  {
    name: "session_id",
    type: "string",
    required: true,
    description: "Identificador da conversa. Reutilize entre mensagens para manter o histórico; gere outro para começar do zero.",
  },
  { name: "message", type: "string", required: true, description: "Texto da mensagem do usuário." },
  {
    name: "agent_type",
    type: "string",
    required: false,
    description: "Slug do agente. Padrão: conversational.",
  },
  {
    name: "dependencies",
    type: "object",
    required: false,
    description:
      "Metadados que você já tem sobre o usuário (cpf, nome, plano…). Viram contexto estruturado no prompt — não é uma tool call.",
  },
];

function ApiReference({ baseUrl }: { baseUrl: string }) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h3 className="text-sm font-semibold">Corpo da requisição</h3>
            <p className="text-[13px] text-muted-foreground">
              O mesmo JSON para <code className="font-mono text-xs">/chat</code> e{" "}
              <code className="font-mono text-xs">/chat/stream</code>.
            </p>
          </div>
          <a
            href={`${baseUrl}/docs`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex shrink-0 items-center gap-1.5 text-[13px] text-primary hover:underline"
          >
            OpenAPI <ExternalLink className="size-3.5" />
          </a>
        </div>
        <Card className="overflow-hidden">
          <div className="scrollbar-thin overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-[13px]">
              <thead className="border-b border-border bg-surface text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Campo</th>
                  <th className="px-4 py-2.5 font-medium">Tipo</th>
                  <th className="px-4 py-2.5 font-medium">Descrição</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {PARAMETERS.map((param) => (
                  <tr key={param.name} className="align-top">
                    <td className="whitespace-nowrap px-4 py-3">
                      <code className="font-mono text-xs font-semibold">{param.name}</code>
                      <div className="mt-1">
                        {param.required ? <Badge>obrigatório</Badge> : <Badge variant="secondary">opcional</Badge>}
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{param.type}</td>
                    <td className="px-4 py-3 text-muted-foreground">{param.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="flex flex-col gap-2 p-5">
          <p className="font-mono text-xs font-semibold">POST /chat</p>
          <p className="text-[13px] text-muted-foreground">
            Aguarda a execução completa e devolve JSON com <code className="font-mono text-xs">agent_type</code>,{" "}
            <code className="font-mono text-xs">session_id</code> e <code className="font-mono text-xs">content</code>.
          </p>
        </Card>
        <Card className="flex flex-col gap-2 p-5">
          <p className="font-mono text-xs font-semibold">POST /chat/stream</p>
          <ul className="flex flex-col gap-1 text-[13px] text-muted-foreground">
            <li>
              <code className="font-mono text-xs text-foreground">event: message</code> — pedaços de texto{" "}
              <code className="font-mono text-xs">{"{content}"}</code>
            </li>
            <li>
              <code className="font-mono text-xs text-foreground">event: usage</code> — total de tokens, ao terminar
            </li>
            <li>
              <code className="font-mono text-xs text-foreground">event: done</code> — fim do stream
            </li>
          </ul>
          <p className="text-xs text-muted-foreground">
            É POST: consuma com <code className="font-mono">fetch</code> lendo o stream, não com{" "}
            <code className="font-mono">EventSource</code>.
          </p>
        </Card>
      </div>
    </div>
  );
}
