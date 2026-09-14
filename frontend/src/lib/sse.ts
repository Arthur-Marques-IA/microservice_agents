/**
 * Parser mínimo de Server-Sent Events para consumir um `Response.body`
 * (ReadableStream) manualmente. Não dá pra usar a API `EventSource` do
 * browser aqui porque ela só suporta GET, e `/api/chat/stream` é POST
 * (a mensagem do usuário vai no corpo, não na query string).
 */
export interface SseEvent {
  event: string;
  data: string;
}

export async function* parseSseStream(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      // sse-starlette manda linhas terminadas em \r\n — normaliza antes de
      // procurar o separador de evento (\n\n), senão \r\n\r\n nunca casa.
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

      let separatorIndex: number;
      while ((separatorIndex = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);

        let event = "message";
        const dataLines: string[] = [];
        for (const line of rawEvent.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        }
        if (dataLines.length > 0) {
          yield { event, data: dataLines.join("\n") };
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
