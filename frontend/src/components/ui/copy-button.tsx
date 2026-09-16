"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";

export function CopyButton({
  value,
  label = "Copiar",
  className,
  size = "icon-xs",
}: {
  value: string;
  label?: string;
  className?: string;
  size?: "icon-xs" | "icon-sm";
}) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard indisponível (ex. contexto não seguro) — sem feedback enganoso.
    }
  }

  return (
    <Button
      variant="ghost"
      size={size}
      onClick={handleCopy}
      aria-label={copied ? "Copiado" : label}
      title={copied ? "Copiado" : label}
      className={cn("text-muted-foreground hover:text-foreground", className)}
    >
      {copied ? <Check className="text-success" /> : <Copy />}
    </Button>
  );
}
