"use client";

import { useEffect } from "react";
import { CircleAlert, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/primitives";
import { SidebarTrigger } from "@/components/workspace/app-shell";

/** Falha inesperada numa tela: a sidebar continua de pé e dá para tentar de novo. */
export default function WorkspaceError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex h-14 shrink-0 items-center border-b border-border px-3 lg:hidden">
        <SidebarTrigger />
      </div>
      <EmptyState
        className="flex-1"
        icon={CircleAlert}
        title="Algo deu errado nesta tela"
        description={
          <>
            {error.message || "Erro inesperado."}
            {error.digest && <span className="mt-1 block font-mono text-xs">ref: {error.digest}</span>}
          </>
        }
        action={
          <Button variant="outline" onClick={() => retry()}>
            <RotateCcw /> Tentar de novo
          </Button>
        }
      />
    </div>
  );
}
