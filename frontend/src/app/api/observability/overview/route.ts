import { proxyJson } from "@/lib/api";

/** Panorama do dashboard dos Logs (`GET /observability/overview`). */
export async function GET(request: Request) {
  const { search } = new URL(request.url);
  return proxyJson(`/observability/overview${search}`);
}
