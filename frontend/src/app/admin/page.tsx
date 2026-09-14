import { backendUrl } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { IngestTextForm } from "@/components/admin/ingest-text-form";
import { UploadFileForm } from "@/components/admin/upload-file-form";
import { SearchPanel } from "@/components/admin/search-panel";

async function getCollections(): Promise<string[]> {
  try {
    const res = await fetch(backendUrl("/collections"), { cache: "no-store" });
    if (!res.ok) return [];
    const data = (await res.json()) as { collections: string[] };
    return data.collections;
  } catch {
    return [];
  }
}

export default async function AdminPage() {
  const collections = await getCollections();

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-4">
      <div>
        <h1 className="text-lg font-semibold">Collections de documentos</h1>
        <p className="text-sm text-muted-foreground">
          Ingestão e busca nas bases de conhecimento (RAG) do agent-service.
        </p>
      </div>

      {collections.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Nenhuma coleção configurada, ou o agent-service está indisponível.
        </p>
      )}

      {collections.map((collection) => (
        <Card key={collection}>
          <CardHeader>
            <CardTitle>{collection}</CardTitle>
            <CardDescription>Tabela pgvector: knowledge_{collection}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <div className="flex flex-col gap-4 sm:flex-row">
              <div className="flex-1">
                <h3 className="mb-2 text-xs font-medium text-muted-foreground">Ingerir texto</h3>
                <IngestTextForm collection={collection} />
              </div>
              <div className="flex-1">
                <h3 className="mb-2 text-xs font-medium text-muted-foreground">Enviar arquivo</h3>
                <UploadFileForm />
              </div>
            </div>
            <div>
              <h3 className="mb-2 text-xs font-medium text-muted-foreground">Buscar</h3>
              <SearchPanel collection={collection} />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
