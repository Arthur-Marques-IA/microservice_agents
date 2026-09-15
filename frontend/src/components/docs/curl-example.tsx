"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CodeBlock } from "@/components/ui/code-block";

function buildCurl(opts: {
  path: "/chat" | "/chat/stream";
  agentType: string;
  withDependencies: boolean;
  baseUrl: string;
}) {
  const body: Record<string, unknown> = {
    agent_type: opts.agentType,
    user_id: "user-123",
    session_id: "session-abc",
    message: "Qual o status do meu pedido?",
  };
  if (opts.withDependencies) {
    body.dependencies = { cpf: "000.000.000-00", nome: "Maria" };
  }
  const flags = opts.path === "/chat/stream" ? "-N " : "";
  return `curl ${flags}-X POST ${opts.baseUrl}${opts.path} \\
  -H "Content-Type: application/json" \\
  -d '${JSON.stringify(body, null, 2)}'`;
}

export function CurlExample({
  agentTypes,
  defaultBaseUrl,
}: {
  agentTypes: string[];
  defaultBaseUrl: string;
}) {
  const [agentType, setAgentType] = useState(agentTypes[0] ?? "conversational");
  const [withDependencies, setWithDependencies] = useState(true);
  const [baseUrl, setBaseUrl] = useState(defaultBaseUrl);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-muted-foreground">URL do agent-service</label>
          <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} className="w-64" />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-muted-foreground">agent_type</label>
          <Select
            value={agentType}
            onChange={(e) => setAgentType(e.target.value)}
            className="w-48"
          >
            {agentTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </Select>
        </div>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={withDependencies}
            onChange={(e) => setWithDependencies(e.target.checked)}
          />
          incluir dependencies (cpf/nome)
        </label>
      </div>

      <Tabs defaultValue="sync">
        <TabsList>
          <TabsTrigger value="sync">/chat (resposta única)</TabsTrigger>
          <TabsTrigger value="stream">/chat/stream (SSE)</TabsTrigger>
        </TabsList>
        <TabsContent value="sync">
          <CodeBlock code={buildCurl({ path: "/chat", agentType, withDependencies, baseUrl })} />
        </TabsContent>
        <TabsContent value="stream">
          <CodeBlock
            code={buildCurl({ path: "/chat/stream", agentType, withDependencies, baseUrl })}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
