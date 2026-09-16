"use client";

import { FormEvent, useId, useRef, useState } from "react";
import { ArrowUp, Braces, Square } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";

export function Composer({
  onSend,
  onStop,
  isStreaming,
  disabled,
  placeholder,
  contextCount,
  contextInvalid,
  onOpenContext,
}: {
  /** Retorna `false` se a mensagem não foi aceita (o texto fica no campo). */
  onSend: (text: string) => boolean;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  placeholder?: string;
  contextCount: number;
  contextInvalid: boolean;
  onOpenContext: () => void;
}) {
  const id = useId();
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const canSend = Boolean(value.trim()) && !isStreaming && !disabled;

  function autoResize(el: HTMLTextAreaElement) {
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }

  function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!canSend) return;
    if (onSend(value)) {
      setValue("");
      if (textareaRef.current) textareaRef.current.style.height = "auto";
    }
  }

  return (
    <form
      onSubmit={submit}
      className={cn(
        "rounded-2xl border border-input bg-card shadow-sm transition-[border-color,box-shadow]",
        "focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/15",
        disabled && "opacity-70"
      )}
    >
      <label htmlFor={id} className="sr-only">
        Mensagem
      </label>
      <textarea
        ref={textareaRef}
        id={id}
        value={value}
        rows={1}
        autoFocus
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => {
          setValue(e.target.value);
          autoResize(e.target);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        className="scrollbar-thin block max-h-60 min-h-[52px] w-full resize-none bg-transparent px-4 pb-1 pt-3.5 text-sm leading-relaxed outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
      />
      <div className="flex items-center gap-2 px-2.5 pb-2.5">
        <button
          type="button"
          onClick={onOpenContext}
          title="Contexto (dependencies) enviado com cada mensagem"
          className={cn(
            "inline-flex h-7 items-center gap-1.5 rounded-lg border px-2 text-xs transition-colors",
            contextInvalid
              ? "border-destructive/40 bg-destructive/5 text-destructive"
              : contextCount > 0
                ? "border-primary/30 bg-primary-soft text-primary"
                : "border-border text-muted-foreground hover:bg-accent hover:text-foreground"
          )}
        >
          <Braces className="size-3.5" />
          {contextInvalid ? "Contexto inválido" : contextCount > 0 ? `Contexto · ${contextCount}` : "Contexto"}
        </button>
        <div className="ml-auto flex items-center gap-3">
          <span className="hidden text-[11px] text-muted-foreground md:inline">
            Enter envia · Shift+Enter quebra linha
          </span>
          {isStreaming ? (
            <Button size="icon-sm" variant="secondary" onClick={onStop} aria-label="Parar resposta" title="Parar resposta">
              <Square className="fill-current" />
            </Button>
          ) : (
            <Button type="submit" size="icon-sm" disabled={!canSend} aria-label="Enviar mensagem" title="Enviar">
              <ArrowUp />
            </Button>
          )}
        </div>
      </div>
    </form>
  );
}
