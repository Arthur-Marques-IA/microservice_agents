import { proxyJson } from "@/lib/api";

export async function GET() {
  return proxyJson("/tools");
}

export async function POST(request: Request) {
  return proxyJson("/tools", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}
