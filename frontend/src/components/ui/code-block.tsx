import { cn } from "@/lib/cn";
import { CopyButton } from "@/components/ui/copy-button";

export function CodeBlock({
  code,
  title,
  className,
}: {
  code: string;
  title?: string;
  className?: string;
}) {
  return (
    <div className={cn("overflow-hidden rounded-xl border border-border bg-surface", className)}>
      <div className="flex h-9 items-center justify-between border-b border-border pl-3.5 pr-1.5">
        <span className="truncate font-mono text-[11px] text-muted-foreground">{title ?? "código"}</span>
        <CopyButton value={code} label="Copiar código" />
      </div>
      <pre className="scrollbar-thin overflow-x-auto p-4 font-mono text-[12.5px] leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}
