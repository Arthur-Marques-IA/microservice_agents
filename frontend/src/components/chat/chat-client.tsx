"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MessageBubble } from "@/components/chat/message-bubble";
import { useChat } from "@/lib/use-chat";

function getOrCreateId(key: string): string {
  if (typeof window === "undefined") return "";
  const existing = window.localStorage.getItem(key);
  if (existing) return existing;
  const created = crypto.randomUUID();
  window.localStorage.setItem(key, created);
  return created;
}

export function ChatClient({ agentTypes }: { agentTypes: string[] }) {
  const [agentType, setAgentType] = useState(agentTypes[0] ?? "conversational");
  const [userId, setUserId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setUserId(getOrCreateId("agent-service:user-id"));
    setSessionId(crypto.randomUUID());
  }, []);

  const { messages, sendMessage, isStreaming, error } = useChat({ agentType, userId, sessionId });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input;
    setInput("");
    void sendMessage(text);
  }

  function startNewSession() {
    setSessionId(crypto.randomUUID());
  }

  if (!userId || !sessionId) return null;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 p-4">
      <div className="flex items-center justify-between gap-2">
        <select
          value={agentType}
          onChange={(e) => setAgentType(e.target.value)}
          className="h-9 rounded-md border border-border bg-card px-3 text-sm"
        >
          {agentTypes.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
        <Button type="button" variant="outline" size="sm" onClick={startNewSession}>
          Nova sessão
        </Button>
      </div>

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto rounded-lg border border-border p-4">
        {messages.length === 0 && (
          <p className="text-sm text-muted-foreground">Envie uma mensagem para começar a conversa.</p>
        )}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        <div ref={bottomRef} />
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <form onSubmit={handleSubmit} className="flex gap-2">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
          placeholder="Digite sua mensagem..."
          rows={2}
          disabled={isStreaming}
        />
        <Button type="submit" disabled={isStreaming || !input.trim()} size="icon">
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}
