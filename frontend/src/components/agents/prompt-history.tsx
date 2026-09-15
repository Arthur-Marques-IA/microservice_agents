"use client";

import { useEffect, useState } from "react";
import type { PromptVersion } from "@/lib/types";

export function PromptHistory({ agentType }: { agentType: string }) {
  const [versions, setVersions] = useState<PromptVersion[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/agents/${agentType}/versions`)
      .then((res) => res.json())
      .then((data: PromptVersion[]) => {
        if (!cancelled) setVersions(data);
      });
    return () => {
      cancelled = true;
    };
  }, [agentType]);

  if (versions === null) return <p className="text-sm text-muted-foreground">Carregando...</p>;

  return (
    <ul className="flex flex-col gap-3">
      {versions.map((v) => (
        <li key={v.version} className="rounded-md border border-border p-3">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-xs font-semibold">versão {v.version}</span>
            <span className="text-xs text-muted-foreground">
              {new Date(v.created_at).toLocaleString("pt-BR")}
            </span>
          </div>
          <p className="whitespace-pre-wrap text-xs text-muted-foreground">
            {v.instructions.join("\n")}
          </p>
        </li>
      ))}
    </ul>
  );
}
