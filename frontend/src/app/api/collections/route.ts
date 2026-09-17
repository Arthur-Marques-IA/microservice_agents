import { proxyJson } from "@/lib/api";

export async function GET() {
  return proxyJson("/collections");
}

export async function POST(request: Request) {
  const body = await request.text();
  return proxyJson("/collections", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
