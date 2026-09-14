import { proxyJson } from "@/lib/api";

export async function POST(request: Request) {
  const body = await request.text();
  return proxyJson("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
