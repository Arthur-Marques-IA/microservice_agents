import { proxyJson } from "@/lib/api";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ type: string; version: string }> },
) {
  const { type, version } = await params;
  return proxyJson(
    `/agents/${encodeURIComponent(type)}/feedback/rollback/${encodeURIComponent(version)}`,
    { method: "POST" },
  );
}
