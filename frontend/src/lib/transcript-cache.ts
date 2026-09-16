import type { ChatMessage } from "@/lib/types";

/**
 * Entrega o histórico de uma conversa recém-criada em `/chat` para a rota
 * `/chat/[sessionId]` sem piscar a tela nem refazer o fetch dos runs logo
 * depois do primeiro envio. Estado de módulo, só no browser.
 */
const cache = new Map<string, { agentType: string; messages: ChatMessage[] }>();

export function stashTranscript(sessionId: string, value: { agentType: string; messages: ChatMessage[] }) {
  cache.set(sessionId, value);
}

export function peekTranscript(sessionId: string) {
  return cache.get(sessionId);
}

export function clearTranscript(sessionId: string) {
  cache.delete(sessionId);
}
