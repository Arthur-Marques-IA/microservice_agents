import { backendUrl } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CurlExample } from "@/components/docs/curl-example";

async function getAgentTypes(): Promise<string[]> {
  try {
    const res = await fetch(backendUrl("/agent-types"), { cache: "no-store" });
    if (!res.ok) return ["conversational"];
    const data = (await res.json()) as { agent_types: string[] };
    return data.agent_types.length > 0 ? data.agent_types : ["conversational"];
  } catch {
    return ["conversational"];
  }
}

export default async function DocsPage() {
  const agentTypes = await getAgentTypes();

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-4">
      <div>
        <h1 className="text-lg font-semibold">Integração via API</h1>
        <p className="text-sm text-muted-foreground">
          Como outros módulos da plataforma conversam com o agent-service — chame direto o
          backend (não é o BFF deste frontend).
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Exemplo cURL</CardTitle>
        </CardHeader>
        <CardContent>
          <CurlExample agentTypes={agentTypes} defaultBaseUrl="http://localhost:58000" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Parâmetros obrigatórios</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="flex flex-col gap-3 text-sm">
            <div>
              <dt className="font-mono text-xs font-semibold">agent_type</dt>
              <dd className="text-muted-foreground">
                Slug do agente (ver <code className="font-mono">GET /agents</code> ou{" "}
                <code className="font-mono">GET /agent-types</code>). Default:{" "}
                <code className="font-mono">conversational</code>.
              </dd>
            </div>
            <div>
              <dt className="font-mono text-xs font-semibold">user_id</dt>
              <dd className="text-muted-foreground">
                Identificador estável do usuário final na sua plataforma — usado para memórias de
                longo prazo do agente.
              </dd>
            </div>
            <div>
              <dt className="font-mono text-xs font-semibold">session_id</dt>
              <dd className="text-muted-foreground">
                Identificador da conversa. Reaproveite o mesmo valor entre mensagens da mesma
                conversa pra manter o histórico; gere um novo pra começar do zero.
              </dd>
            </div>
            <div>
              <dt className="font-mono text-xs font-semibold">message</dt>
              <dd className="text-muted-foreground">Texto da mensagem do usuário.</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Parâmetros opcionais</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="flex flex-col gap-3 text-sm">
            <div>
              <dt className="font-mono text-xs font-semibold">dependencies</dt>
              <dd className="text-muted-foreground">
                Objeto livre com metadados que você já tem sobre o usuário (ex:{" "}
                <code className="font-mono">cpf</code>, <code className="font-mono">nome</code>,
                plano, região) — vira contexto estruturado injetado no prompt do agente. Não é uma
                tool call: o agente só &quot;enxerga&quot; esses dados como informação de fundo pra
                personalizar a resposta.
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Resposta</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm text-muted-foreground">
          <p>
            <code className="font-mono text-foreground">POST /chat</code> devolve JSON com{" "}
            <code className="font-mono">content</code> (a resposta completa).
          </p>
          <p>
            <code className="font-mono text-foreground">POST /chat/stream</code> devolve
            Server-Sent Events: um ou mais <code className="font-mono">event: message</code> com
            pedaços de texto (<code className="font-mono">{"{content: string}"}</code>), depois um{" "}
            <code className="font-mono">event: usage</code> com o total de tokens consumidos (não
            é incremental — só chega quando a resposta termina), e por fim{" "}
            <code className="font-mono">event: done</code>. Como é <code className="font-mono">POST</code>,
            não dá pra consumir com <code className="font-mono">EventSource</code> do browser — use{" "}
            <code className="font-mono">fetch</code> e leia o <code className="font-mono">ReadableStream</code>{" "}
            manualmente.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
