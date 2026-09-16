import { proxyJson } from "@/lib/api";

/** Se `CUSTOM_PYTHON_TOOLS_ENABLED` está ligado no agent-service. */
export async function GET() {
  return proxyJson("/tools/python-config");
}
