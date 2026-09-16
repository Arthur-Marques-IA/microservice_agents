/**
 * Gera exemplos de integração com o contrato estável do agent-service
 * (`POST /chat` e `POST /chat/stream`) — são chamadas diretas ao backend,
 * como outro módulo da plataforma faria, não ao BFF deste frontend.
 */

export type SnippetLanguage = "curl" | "javascript" | "python";
export type ChatEndpoint = "/chat" | "/chat/stream";

export interface SnippetOptions {
  baseUrl: string;
  endpoint: ChatEndpoint;
  agentType: string;
  userId: string;
  sessionId: string;
  message: string;
  dependencies?: Record<string, unknown> | null;
}

export const SNIPPET_LANGUAGES: { value: SnippetLanguage; label: string }[] = [
  { value: "curl", label: "cURL" },
  { value: "javascript", label: "JavaScript" },
  { value: "python", label: "Python" },
];

function buildPayload(opts: SnippetOptions): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    agent_type: opts.agentType,
    user_id: opts.userId,
    session_id: opts.sessionId,
    message: opts.message,
  };
  if (opts.dependencies && Object.keys(opts.dependencies).length > 0) {
    payload.dependencies = opts.dependencies;
  }
  return payload;
}

function indent(text: string, spaces: number): string {
  const pad = " ".repeat(spaces);
  return text
    .split("\n")
    .map((line, i) => (i === 0 ? line : pad + line))
    .join("\n");
}

function toPython(value: unknown, level = 0): string {
  const pad = "    ".repeat(level + 1);
  const closePad = "    ".repeat(level);
  if (value === null || value === undefined) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    return `[\n${value.map((v) => pad + toPython(v, level + 1)).join(",\n")},\n${closePad}]`;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value);
    if (entries.length === 0) return "{}";
    return `{\n${entries
      .map(([k, v]) => `${pad}${JSON.stringify(k)}: ${toPython(v, level + 1)}`)
      .join(",\n")},\n${closePad}}`;
  }
  return JSON.stringify(String(value));
}

function curl(opts: SnippetOptions): string {
  const body = JSON.stringify(buildPayload(opts), null, 2).replace(/'/g, "'\\''");
  const flags = opts.endpoint === "/chat/stream" ? "-N " : "";
  return `curl ${flags}-X POST ${opts.baseUrl}${opts.endpoint} \\
  -H "Content-Type: application/json" \\
  -d '${body}'`;
}

function javascript(opts: SnippetOptions): string {
  const body = indent(JSON.stringify(buildPayload(opts), null, 2), 2);
  const request = `const response = await fetch("${opts.baseUrl}${opts.endpoint}", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(${body}),
});`;

  if (opts.endpoint === "/chat") {
    return `${request}

const { content } = await response.json();
console.log(content);`;
  }

  return `${request}

// SSE via POST: leia o stream manualmente (EventSource só faz GET).
const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
let buffer = "";
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += value.replaceAll("\\r\\n", "\\n");
  let index;
  while ((index = buffer.indexOf("\\n\\n")) !== -1) {
    const rawEvent = buffer.slice(0, index);
    buffer = buffer.slice(index + 2);
    const event = rawEvent.match(/^event: ?(.*)$/m)?.[1];
    const data = rawEvent.match(/^data: ?(.*)$/m)?.[1];
    if (event === "message") process.stdout.write(JSON.parse(data).content);
    if (event === "usage") console.log("\\n", JSON.parse(data));
  }
}`;
}

function python(opts: SnippetOptions): string {
  const payload = toPython(buildPayload(opts));

  if (opts.endpoint === "/chat") {
    return `import requests

payload = ${payload}

response = requests.post("${opts.baseUrl}/chat", json=payload, timeout=120)
response.raise_for_status()
print(response.json()["content"])`;
  }

  return `import json
import httpx

payload = ${payload}

with httpx.stream("POST", "${opts.baseUrl}/chat/stream", json=payload, timeout=None) as response:
    event = None
    for line in response.iter_lines():
        if line.startswith("event:"):
            event = line.removeprefix("event:").strip()
        elif line.startswith("data:") and event == "message":
            chunk = json.loads(line.removeprefix("data:").strip())
            print(chunk["content"], end="", flush=True)`;
}

export function buildSnippet(language: SnippetLanguage, opts: SnippetOptions): string {
  if (language === "javascript") return javascript(opts);
  if (language === "python") return python(opts);
  return curl(opts);
}
