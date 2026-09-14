"use client";

import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { SearchResult } from "@/lib/types";

export function SearchPanel({ collection }: { collection: string }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/collections/${collection}/search?${new URLSearchParams({ query, limit: "5" })}`
      );
      if (!res.ok) throw new Error(`Falha na busca (HTTP ${res.status})`);
      setResults((await res.json()) as SearchResult[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro desconhecido");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input placeholder="Buscar na coleção..." value={query} onChange={(e) => setQuery(e.target.value)} />
        <Button type="submit" size="sm" disabled={loading || !query.trim()}>
          Buscar
        </Button>
      </form>
      {error && <p className="text-xs text-destructive">{error}</p>}
      {results && results.length === 0 && (
        <p className="text-xs text-muted-foreground">Nenhum resultado encontrado.</p>
      )}
      {results && results.length > 0 && (
        <ul className="flex flex-col gap-2">
          {results.map((result, i) => (
            <li key={i} className="rounded-md bg-muted p-2 text-xs">
              {result.content}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
