"use client";

import { useEffect, useState } from "react";
import { GraduationCap, History, Plus, RotateCcw, Trash } from "lucide-react";
import { errorMessage, requestJson } from "@/lib/http";
import type { FeedbackNote, FeedbackRule, FeedbackVersion } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { sessionTitle } from "@/lib/sessions";
import { useWorkspace } from "@/components/workspace/workspace-provider";
import { EmptyState, RelativeTime, SectionHeading, Skeleton } from "@/components/ui/primitives";
import { useConfirm } from "@/components/ui/confirm";
import { useToast } from "@/components/ui/toast";

/**
 * As regras de comportamento que o agente aprendeu com feedback. Elas são
 * concatenadas às instructions em runtime, sem virar uma versão de prompt —
 * por isso ficam aqui e não no histórico de versões.
 *
 * Duas formas de ensinar: o feedback em texto sobre uma conversa (`POST`), que
 * a IA mescla nas regras que já existem — aqui ou no chat, pelo polegar para
 * baixo —, e a regra escrita à mão (`PUT`), que não passa pelo modelo e é a
 * saída quando um merge sai errado.
 */
export function FeedbackPanel({ agentType }: { agentType: string }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [note, setNote] = useState<FeedbackNote | null>(null);
  const [loading, setLoading] = useState(true);
  const [versions, setVersions] = useState<FeedbackVersion[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [nova, setNova] = useState("");
  const { sessions } = useWorkspace();
  const conversas = sessions.filter((s) => s.agent_id === agentType);
  const [sessaoEscolhida, setSessaoEscolhida] = useState("");
  const sessao = sessaoEscolhida || conversas[0]?.session_id || "";
  const [comentario, setComentario] = useState("");

  const base = `/api/agents/${encodeURIComponent(agentType)}/feedback`;

  useEffect(() => {
    let vivo = true;
    requestJson<FeedbackNote>(base, { fallbackError: "" })
      .then((data) => vivo && setNote(data))
      // 404 é o estado normal de quem ainda não recebeu feedback nenhum.
      .catch(() => vivo && setNote(null))
      .finally(() => vivo && setLoading(false));
    return () => {
      vivo = false;
    };
  }, [base]);

  async function salvar(rules: FeedbackRule[], mensagem: string) {
    setSaving(true);
    try {
      setNote(
        await requestJson<FeedbackNote>(base, {
          method: "PUT",
          json: { rules: rules.map((r) => ({ id: r.id, texto: r.texto })) },
          fallbackError: "Falha ao salvar as regras",
        })
      );
      setVersions(null);
      toast({ title: mensagem, description: "Vale a partir da próxima mensagem.", variant: "success" });
    } catch (err) {
      toast({ title: "Não deu para salvar", description: errorMessage(err), variant: "error" });
    } finally {
      setSaving(false);
    }
  }

  async function ensinar() {
    const feedback = comentario.trim();
    if (!feedback || !sessao) return;
    setSaving(true);
    try {
      const atualizada = await requestJson<FeedbackNote>(base, {
        method: "POST",
        json: { session_id: sessao, feedback },
        fallbackError: "Falha ao ensinar o agente",
      });
      setNote(atualizada);
      setVersions(null);
      setComentario("");
      const mudou = Object.entries(atualizada.diff ?? {}).flatMap(([tipo, itens]) =>
        (itens ?? []).map((item) => `${tipo}: ${item}`)
      );
      toast({
        title: `Agente ajustado (v${atualizada.version})`,
        description: mudou.length > 0 ? mudou.join(" · ") : "Nenhuma regra mudou — o feedback já estava coberto.",
        variant: "success",
      });
    } catch (err) {
      toast({ title: "Não deu para ensinar", description: errorMessage(err), variant: "error" });
    } finally {
      setSaving(false);
    }
  }

  async function remover(rule: FeedbackRule) {
    const restantes = (note?.rules ?? []).filter((r) => r.id !== rule.id);
    if (restantes.length === 0) {
      await limpar();
      return;
    }
    await salvar(restantes, "Regra removida");
  }

  async function limpar() {
    const ok = await confirm({
      title: "Zerar o que o agente aprendeu?",
      description: "Apaga as regras e o histórico delas. O agente volta a valer só pelas instructions.",
      confirmLabel: "Zerar",
      destructive: true,
    });
    if (!ok) return;
    setSaving(true);
    try {
      await requestJson(base, { method: "DELETE", fallbackError: "Falha ao zerar" });
      setNote(null);
      setVersions(null);
      toast({ title: "Nota zerada", variant: "success" });
    } catch (err) {
      toast({ title: "Não deu para zerar", description: errorMessage(err), variant: "error" });
    } finally {
      setSaving(false);
    }
  }

  async function voltarPara(version: number) {
    setSaving(true);
    try {
      setNote(
        await requestJson<FeedbackNote>(`${base}/rollback/${version}`, {
          method: "POST",
          fallbackError: "Falha ao restaurar",
        })
      );
      setVersions(null);
      toast({ title: `Regras da v${version} restauradas`, variant: "success" });
    } catch (err) {
      toast({ title: "Não deu para restaurar", description: errorMessage(err), variant: "error" });
    } finally {
      setSaving(false);
    }
  }

  async function verHistorico() {
    if (versions) {
      setVersions(null);
      return;
    }
    try {
      setVersions(await requestJson<FeedbackVersion[]>(`${base}/versions`, { fallbackError: "Falha ao ler o histórico" }));
    } catch (err) {
      toast({ title: "Não deu para ler o histórico", description: errorMessage(err), variant: "error" });
    }
  }

  if (loading) {
    return (
      <Card className="flex flex-col gap-3 p-4">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-9" />
        ))}
      </Card>
    );
  }

  const rules = note?.rules ?? [];

  return (
    <div className="flex flex-col gap-4">
      <SectionHeading
        title="O que o agente aprendeu"
        description="Regras que entram nas instructions em toda chamada, sem virar uma versão de prompt. Nascem do feedback dado numa conversa."
        action={
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={verHistorico} disabled={!note}>
              <History /> Histórico
            </Button>
            <Button variant="outline" size="sm" onClick={limpar} disabled={!note || saving}>
              <Trash /> Zerar
            </Button>
          </div>
        }
      />

      {rules.length === 0 ? (
        <Card>
          <EmptyState
            title="Nada aprendido ainda"
            description="No chat, o polegar para baixo numa resposta pergunta o que deveria ter sido diferente — e o que você escrever vira uma regra aqui."
          />
        </Card>
      ) : (
        <Card className="flex flex-col gap-2 p-4">
          <p className="text-xs text-muted-foreground">
            versão {note?.version} · {rules.length} {rules.length === 1 ? "regra" : "regras"}
          </p>
          {rules.map((rule) => (
            <div key={rule.id} className="flex items-start gap-2">
              <Input
                value={rule.texto}
                onChange={(e) =>
                  setNote((prev) =>
                    prev
                      ? { ...prev, rules: prev.rules.map((r) => (r.id === rule.id ? { ...r, texto: e.target.value } : r)) }
                      : prev
                  )
                }
                onBlur={(e) => {
                  const texto = e.target.value.trim();
                  const anterior = rules.find((r) => r.id === rule.id)?.texto;
                  if (!texto || texto === anterior) return;
                  void salvar(
                    rules.map((r) => (r.id === rule.id ? { ...r, texto } : r)),
                    "Regra atualizada"
                  );
                }}
                className="flex-1"
                aria-label="Texto da regra"
              />
              <Button
                variant="ghost"
                size="icon"
                aria-label="Remover regra"
                disabled={saving}
                onClick={() => void remover(rule)}
              >
                <Trash className="size-4" />
              </Button>
            </div>
          ))}
        </Card>
      )}

      <Card className="flex flex-col gap-3 p-4">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <GraduationCap className="size-4" /> Dar feedback sobre uma conversa
        </div>
        {conversas.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">
            Converse com o agente no Playground primeiro: o feedback é sobre uma conversa, e a IA lê a transcrição
            para transformar o comentário em regra. (No chat, o 👎 de uma resposta faz o mesmo.)
          </p>
        ) : (
          <>
            <Select
              aria-label="Conversa"
              value={sessao}
              onChange={(e) => setSessaoEscolhida(e.target.value)}
            >
              {conversas.map((s) => (
                <option key={s.session_id} value={s.session_id}>
                  {sessionTitle(s)}
                </option>
              ))}
            </Select>
            <Textarea
              value={comentario}
              onChange={(e) => setComentario(e.target.value)}
              rows={3}
              placeholder="O que o agente deveria ter feito diferente nessa conversa? (ex.: confirmar o CPF antes de dar detalhes da fatura)"
              className="text-[13px]"
            />
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">
                A IA mescla o comentário nas regras atuais (edita, remove ou acrescenta) e mostra o que mudou.
              </p>
              <Button disabled={!comentario.trim() || !sessao || saving} onClick={() => void ensinar()}>
                <GraduationCap /> Ensinar
              </Button>
            </div>
          </>
        )}
      </Card>

      <Card className="flex items-start gap-2 p-4">
        <Input
          value={nova}
          onChange={(e) => setNova(e.target.value)}
          placeholder="Escrever uma regra à mão (ex.: Sempre confirme o CPF antes de dar detalhes da conta)"
          className="flex-1"
          onKeyDown={(e) => {
            if (e.key !== "Enter" || !nova.trim()) return;
            e.preventDefault();
            void salvar([...rules, { id: "", texto: nova.trim() }], "Regra adicionada").then(() => setNova(""));
          }}
        />
        <Button
          variant="outline"
          disabled={!nova.trim() || saving}
          onClick={() => void salvar([...rules, { id: "", texto: nova.trim() }], "Regra adicionada").then(() => setNova(""))}
        >
          <Plus /> Adicionar
        </Button>
      </Card>

      {versions && (
        <Card className="divide-y divide-border overflow-hidden">
          {versions.length === 0 ? (
            <p className="px-4 py-3 text-[13px] text-muted-foreground">Sem histórico.</p>
          ) : (
            versions.map((v) => (
              <div key={v.version} className="flex items-center gap-3 px-4 py-3">
                <Badge variant="secondary">v{v.version}</Badge>
                <span className="text-xs text-muted-foreground">{ORIGENS[v.origin] ?? v.origin}</span>
                <span className="min-w-0 flex-1 truncate text-[13px]">
                  {v.rules.map((r) => r.texto).join(" · ") || "(vazia)"}
                </span>
                <RelativeTime date={v.created_at} className="shrink-0 text-xs text-muted-foreground" />
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={saving || v.version === note?.version}
                  onClick={() => void voltarPara(v.version)}
                >
                  <RotateCcw /> Restaurar
                </Button>
              </div>
            ))
          )}
        </Card>
      )}
    </div>
  );
}

const ORIGENS: Record<string, string> = {
  merge: "de um feedback",
  manual: "editada aqui",
  rollback: "restaurada",
};
