/**
 * Helpers de fetch do lado do browser (sempre contra o BFF em `/api/**`).
 * Centraliza a extração da mensagem de erro do FastAPI — `detail` pode ser
 * uma string ou a lista de erros de validação do Pydantic.
 */

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
  const detail = body?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item: { msg?: string; loc?: unknown[] }) => {
        const field = Array.isArray(item.loc) ? item.loc.filter((p) => p !== "body").join(".") : "";
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .filter(Boolean)
      .join(" · ");
  }
  return `${fallback} (HTTP ${response.status})`;
}

export async function requestJson<T>(
  url: string,
  { json, fallbackError = "Falha na requisição", ...init }: RequestInit & { json?: unknown; fallbackError?: string } = {}
): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    ...init,
    ...(json !== undefined && {
      body: JSON.stringify(json),
      headers: { "Content-Type": "application/json", ...init.headers },
    }),
  });
  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response, fallbackError), response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Erro desconhecido";
}
