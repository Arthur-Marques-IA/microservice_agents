import type { ToolFailureKind } from "@/lib/types";

/** Tipos de falha de tool (`tools/failures.py`): o rótulo e o que fazer com cada um. */
export const TOOL_FAILURE_META: Record<ToolFailureKind, { label: string; action: string }> = {
  invalid_arguments: {
    label: "Argumento inválido",
    action: "O modelo chamou com dado faltando ou errado — ajuste as instructions ou a descrição dos parâmetros.",
  },
  not_found: {
    label: "Não encontrado",
    action: "A API respondeu 404. Pode ser uma resposta normal (nada a mostrar) ou um id errado.",
  },
  auth: {
    label: "Autenticação",
    action: "A API recusou a credencial (401/403) — confira a autenticação da tool.",
  },
  unavailable: {
    label: "Sistema indisponível",
    action: "Erro 5xx, limite de requisições ou falha de rede — o problema está no sistema chamado.",
  },
  config: {
    label: "Configuração",
    action: "Destino bloqueado (TOOL_EGRESS_ALLOWLIST) ou dependency que a requisição não mandou.",
  },
  exception: {
    label: "Erro no código da tool",
    action: "A tool levantou uma exceção — veja a mensagem no trace.",
  },
};

export function toolFailureLabel(kind: string | null | undefined): string {
  return (kind && TOOL_FAILURE_META[kind as ToolFailureKind]?.label) || "Falha";
}
