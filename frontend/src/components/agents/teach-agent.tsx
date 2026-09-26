"use client";

import { useState } from "react";
import { GraduationCap } from "lucide-react";
import { errorMessage, requestJson } from "@/lib/http";
import type { FeedbackNote } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/primitives";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";

/**
 * Feedback em texto sobre uma conversa (`POST /agents/{tipo}/feedback`): a IA lê
 * a transcrição da sessão e mescla o comentário nas regras do agente — edita,
 * remove ou acrescenta — e a resposta traz o que mudou.
 *
 * O backend lê a sessão pelo id, sem filtrar usuário: dá para ensinar a partir
 * de qualquer conversa, inclusive as que chegaram pela API (Logs), não só as
 * deste navegador. Só vale para agente conversacional.
 */
export function TeachAgent({
  agentType,
  sessionId,
  onTaught,
}: {
  agentType: string;
  sessionId: string;
  onTaught?: (note: FeedbackNote) => void;
}) {
  const toast = useToast();
  const [texto, setTexto] = useState("");
  const [sending, setSending] = useState(false);

  async function ensinar() {
    const feedback = texto.trim();
    if (!feedback || sending) return;
    setSending(true);
    try {
      const note = await requestJson<FeedbackNote>(`/api/agents/${encodeURIComponent(agentType)}/feedback`, {
        method: "POST",
        json: { session_id: sessionId, feedback },
        fallbackError: "Falha ao ensinar o agente",
      });
      const mudou = Object.entries(note.diff ?? {}).flatMap(([tipo, itens]) =>
        (itens ?? []).map((item) => `${tipo}: ${item}`)
      );
      toast({
        title: `Agente ajustado (v${note.version})`,
        description: mudou.length > 0 ? mudou.join(" · ") : "Nenhuma regra mudou — o feedback já estava coberto.",
        variant: "success",
      });
      setTexto("");
      onTaught?.(note);
    } catch (err) {
      toast({ title: "Não deu para ensinar", description: errorMessage(err), variant: "error" });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Textarea
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        rows={3}
        placeholder="O que o agente deveria ter feito diferente nessa conversa? (ex.: confirmar o CPF antes de dar detalhes da fatura)"
        className="text-[13px]"
      />
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          A IA mescla o comentário nas regras atuais do agente (aba Aprendizado) e mostra o que mudou.
        </p>
        <Button disabled={!texto.trim() || sending} onClick={() => void ensinar()}>
          {sending ? <Spinner /> : <GraduationCap />} Ensinar
        </Button>
      </div>
    </div>
  );
}
