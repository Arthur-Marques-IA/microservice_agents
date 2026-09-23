import { proxyJson } from "@/lib/api";

/** Remove um documento da coleção — o texto e os vetores dele. */
export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ name: string; contentId: string }> },
) {
  const { name, contentId } = await params;
  return proxyJson(
    `/collections/${encodeURIComponent(name)}/documents/${encodeURIComponent(contentId)}`,
    { method: "DELETE" },
  );
}
