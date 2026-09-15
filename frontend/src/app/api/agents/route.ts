import { proxyJson } from "@/lib/api";

export async function GET() {
  return proxyJson("/agents");
}

export async function POST(request: Request) {
  const body = await request.text();
  return proxyJson("/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
