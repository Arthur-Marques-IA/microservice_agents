"use client";

import { FormEvent, useId, useState } from "react";
import { ArrowRight, Search } from "lucide-react";
import { cn } from "@/lib/cn";
import { errorMessage, requestJson } from "@/lib/http";
import type { SearchResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { EmptyState, Spinner } from "@/components/ui/primitives";

type SearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; query: string; results: SearchResult[] }
  | { status: "error"; message: string };

export function SearchPanel({ collection }: { collection: string }) {
  const id = useId();
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState("5");
  const [state, setState] = useState<SearchState>({ status: "idle" });
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set());

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setState({ status: "loading" });
    setExpanded(new Set());
    try {
      const results = await requestJson<SearchResult[]>(
        `/api/collections/${encodeURIComponent(collection)}/search?${new URLSearchParams({ query: q, limit })}`,
        { fallbackError: "Falha na busca" }
      );
      setState({ status: "done", query: q, results });
    } catch (err) {
      setState({ status: "error", message: errorMessage(err) });
    }
  }

  function toggle(index: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  return (
    <Card className="xl:sticky xl:top-0">
      <CardHeader className="pb-4">
        <CardTitle className="flex items-center gap-2">
          <Search className="size-4 text-muted-foreground" /> Testar busca semântica
        </CardTitle>
        <CardDescription>Veja quais trechos da coleção seriam recuperados para uma pergunta.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <label htmlFor={`${id}-query`} className="sr-only">
            Pergunta
          </label>
          <Input
            id={`${id}-query`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ex.: prazo de reembolso"
          />
          <Select
            aria-label="Quantidade de resultados"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            wrapperClassName="w-[4.5rem] shrink-0"
          >
            {["3", "5", "10"].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </Select>
          <Button
            type="submit"
            size="icon"
            disabled={!query.trim() || state.status === "loading"}
            aria-label="Buscar"
          >
            {state.status === "loading" ? <Spinner /> : <ArrowRight />}
          </Button>
        </form>

        {state.status === "idle" && (
          <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-[13px] text-muted-foreground">
            Os trechos aparecem aqui, ordenados por relevância.
          </p>
        )}

        {state.status === "error" && <p className="text-[13px] text-destructive">{state.message}</p>}

        {state.status === "done" && state.results.length === 0 && (
          <EmptyState
            className="py-6"
            icon={Search}
            title="Nenhum trecho encontrado"
            description={`Nada relevante para “${state.query}”.`}
          />
        )}

        {state.status === "done" && state.results.length > 0 && (
          <ol className="flex flex-col gap-2" aria-label="Resultados da busca">
            {state.results.map((result, index) => {
              const isOpen = expanded.has(index);
              const metadata = Object.entries(result.metadata ?? {})
                .filter(([, value]) => value !== null && typeof value !== "object")
                .slice(0, 4);
              return (
                <li key={index} className="rounded-lg border border-border bg-surface p-3">
                  <div className="mb-1.5 flex items-center justify-between text-[11px] text-muted-foreground">
                    <span className="font-medium">#{index + 1}</span>
                    {result.content.length > 280 && (
                      <button type="button" onClick={() => toggle(index)} className="hover:text-foreground">
                        {isOpen ? "Mostrar menos" : "Mostrar tudo"}
                      </button>
                    )}
                  </div>
                  <p className={cn("whitespace-pre-wrap break-words text-[13px] leading-relaxed", !isOpen && "line-clamp-5")}>
                    {result.content}
                  </p>
                  {metadata.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {metadata.map(([key, value]) => (
                        <span key={key} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                          {key}: {String(value)}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
