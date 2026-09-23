/**
 * Anexos de `/chat` e `/analyze`: o backend recebe base64 no corpo JSON, então
 * o arquivo é lido aqui mesmo.
 *
 * O limite espelha o `MAX_ATTACHMENT_MB` do backend (20MB) — recusar antes de
 * ler evita carregar na memória do browser algo que o servidor vai rejeitar.
 */

import type { Attachment } from "@/lib/types";

export const MAX_ATTACHMENT_MB = 20;

export async function readAttachment(file: File): Promise<Attachment> {
  if (file.size > MAX_ATTACHMENT_MB * 1024 * 1024) {
    throw new Error(`${file.name} tem mais de ${MAX_ATTACHMENT_MB}MB — o limite por anexo.`);
  }
  const buffer = await file.arrayBuffer();
  let binario = "";
  const bytes = new Uint8Array(buffer);
  // Em blocos: `String.fromCharCode(...bytes)` de um arquivo grande estoura a
  // pilha de argumentos.
  for (let i = 0; i < bytes.length; i += 8192) {
    binario += String.fromCharCode(...bytes.subarray(i, i + 8192));
  }
  return {
    content_base64: btoa(binario),
    mime_type: file.type || null,
    filename: file.name,
  };
}
