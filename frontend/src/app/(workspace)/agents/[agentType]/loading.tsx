import { Skeleton } from "@/components/ui/primitives";

export default function AgentLoading() {
  return (
    <div className="flex min-h-0 flex-1 flex-col" aria-busy="true" aria-label="Carregando agente">
      <div className="border-b border-border">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 pt-5 sm:px-6 lg:px-8">
          <Skeleton className="h-4 w-32" />
          <div className="flex items-center gap-3">
            <Skeleton className="size-7 rounded-lg" />
            <Skeleton className="h-6 w-56" />
          </div>
          <Skeleton className="h-5 w-80" />
          <div className="flex gap-6 pt-2">
            {[96, 72, 88, 80].map((width) => (
              <Skeleton key={width} className="mb-3 h-4" style={{ width }} />
            ))}
          </div>
        </div>
      </div>
      <div className="mx-auto grid w-full max-w-6xl gap-6 px-4 py-8 sm:px-6 lg:grid-cols-[260px_1fr] lg:px-8">
        <div className="flex flex-col gap-2">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-48" />
        </div>
        <Skeleton className="h-48 rounded-xl" />
      </div>
    </div>
  );
}
