"use client";

import { FormEvent, ReactNode, useEffect, useId, useMemo, useState } from "react";
import Link from "next/link";
import { Plus, Trash, Wrench } from "lucide-react";
import { cn } from "@/lib/cn";
import { errorMessage } from "@/lib/http";
import { formatNumber, slugify } from "@/lib/format";
import { DEFAULT_MODEL, MEMORY_BACKENDS, MODEL_OPTIONS, TOOL_KIND_META, type ModelOption } from "@/lib/agent-meta";
import type {
  AgentDefinition,
  AgentDefinitionInput,
  AgentKind,
  DependencyField,
  DependencyFieldType,
  MemoryBackend,
  ModelParams,
  ModelProviderSummary,
  SchemaField,
  ToolSummary,
} from "@/lib/types";
import { SchemaFieldsEditor, emptyField, schemaProblem } from "@/components/schema/schema-fields-editor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Field, Spinner } from "@/components/ui/primitives";
import { CopyButton } from "@/components/ui/copy-button";
import { useWorkspace } from "@/components/workspace/workspace-provider";

export type AgentFormPayload = Partial<AgentDefinitionInput>;

const SLUG_PATTERN = /^[a-z0-9][a-z0-9_-]*$/;
const DEPENDENCY_FIELD_TYPES: DependencyFieldType[] = ["string", "integer", "number", "boolean"];

const AGENT_KINDS: { kind: AgentKind; label: string; description: string }[] = [
  {
    kind: "conversational",
    label: "Conversacional",
    description: "Mantém a conversa por session_id e responde texto. Aceita nota de feedback.",
  },
  {
    kind: "analysis",
    label: "Analista",
    description: "One-shot no /analyze: recebe um documento e devolve o objeto do response_schema.",
  },
];

interface FormValues {
  agentType: string;
  name: string;
  kind: AgentKind;
  responseSchema: SchemaField[];
  instructions: string;
  tools: string[];
  modelId: string;
  /** "" = usa a credencial padrão do provedor (a mais antiga habilitada). */
  credentialId: string;
  /** "" = agente sem base de conhecimento. */
  knowledgeCollection: string;
  dependencyFields: DependencyField[];
  memoryBackend: MemoryBackend;
  numHistoryRuns: number;
  /** Parâmetros de geração como texto: "" = padrão do provedor. */
  temperature: string;
  topP: string;
  maxTokens: string;
  thinkingBudget: string;
  /** "" = RUN_TIMEOUT_SECONDS do serviço. */
  timeoutSeconds: string;
}

const asText = (value: number | null | undefined) => (value === null || value === undefined ? "" : String(value));

/** Faixas iguais às do backend (`models/params.py`). */
const PARAM_LIMITS = {
  temperature: { min: 0, max: 2, integer: false, label: "Temperatura" },
  topP: { min: 0, max: 1, integer: false, label: "top_p" },
  maxTokens: { min: 1, max: 200000, integer: true, label: "Máx. de tokens" },
  thinkingBudget: { min: 0, max: 32768, integer: true, label: "Orçamento de raciocínio" },
  timeoutSeconds: { min: 1, max: 600, integer: true, label: "Tempo limite" },
} as const;

function numberProblem(key: keyof typeof PARAM_LIMITS, raw: string): string | null {
  if (raw.trim() === "") return null;
  const limits = PARAM_LIMITS[key];
  const value = Number(raw);
  if (Number.isNaN(value)) return `${limits.label}: use um número.`;
  if (limits.integer && !Number.isInteger(value)) return `${limits.label}: use um número inteiro.`;
  if (value < limits.min || value > limits.max) return `${limits.label}: entre ${limits.min} e ${limits.max}.`;
  return null;
}

/** Os parâmetros do formulário no formato da API; `null` = padrão do provedor.
 * `thinking_budget` só vai para o google — em outro provedor o backend recusa. */
function paramsFrom(values: FormValues, provider: string | undefined): ModelParams | null {
  const params: ModelParams = {};
  if (values.temperature.trim()) params.temperature = Number(values.temperature);
  if (values.topP.trim()) params.top_p = Number(values.topP);
  if (values.maxTokens.trim()) params.max_tokens = Number(values.maxTokens);
  if (values.thinkingBudget.trim() && (provider ?? "google") === "google") {
    params.thinking_budget = Number(values.thinkingBudget);
  }
  return Object.keys(params).length ? params : null;
}

function sameParams(a: ModelParams | null | undefined, b: ModelParams | null | undefined) {
  const norm = (p: ModelParams | null | undefined) =>
    JSON.stringify(Object.entries(p ?? {}).sort(([x], [y]) => x.localeCompare(y)));
  return norm(a) === norm(b);
}

function valuesFrom(agent?: AgentDefinition, instructions?: string[]): FormValues {
  return {
    agentType: agent?.agent_type ?? "",
    name: agent?.name ?? "",
    kind: agent?.kind ?? "conversational",
    responseSchema: agent?.response_schema ?? [],
    instructions: (instructions ?? agent?.instructions ?? []).join("\n"),
    tools: agent?.tools ?? [],
    modelId: agent?.model_id ?? DEFAULT_MODEL.id,
    credentialId: agent?.model_credential_id ?? "",
    knowledgeCollection: agent?.knowledge_collection ?? "",
    dependencyFields: agent?.dependency_fields ?? [],
    memoryBackend: agent?.memory_backend ?? "common",
    numHistoryRuns: agent?.num_history_runs ?? 10,
    temperature: asText(agent?.model_params?.temperature),
    topP: asText(agent?.model_params?.top_p),
    maxTokens: asText(agent?.model_params?.max_tokens),
    thinkingBudget: asText(agent?.model_params?.thinking_budget),
    timeoutSeconds: asText(agent?.timeout_seconds),
  };
}

function sameDependencyFields(a: DependencyField[], b: DependencyField[]) {
  return (
    a.length === b.length &&
    a.every((f, i) => f.name === b[i].name && f.type === b[i].type && f.label === b[i].label && f.required === b[i].required)
  );
}

function toLines(text: string) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function sameList(a: string[], b: string[]) {
  return a.length === b.length && a.every((value, i) => value === b[i]);
}

/** Agrupa as opções de modelo pelo rótulo do provedor, pros `<optgroup>` do seletor. */
function groupByProvider(models: ModelOption[], providers: ModelProviderSummary[]): Record<string, ModelOption[]> {
  const labelByProvider = new Map(providers.map((p) => [p.provider, p.label]));
  const groups: Record<string, ModelOption[]> = {};
  for (const model of models) {
    const label = labelByProvider.get(model.provider) ?? model.provider;
    (groups[label] ??= []).push(model);
  }
  return groups;
}

/** Só os campos alterados — assim editar o nome não gera uma versão nova do prompt. */
function buildUpdate(values: FormValues, agent: AgentDefinition, models: ModelOption[]): AgentFormPayload {
  const payload: AgentFormPayload = {};
  if (values.name.trim() !== agent.name) payload.name = values.name.trim();
  const instructions = toLines(values.instructions);
  if (!sameList(instructions, agent.instructions)) payload.instructions = instructions;
  if (!sameList([...values.tools].sort(), [...agent.tools].sort())) payload.tools = values.tools;
  if (values.modelId !== (agent.model_id ?? DEFAULT_MODEL.id)) {
    const model = models.find((m) => m.id === values.modelId) ?? DEFAULT_MODEL;
    payload.model_provider = model.provider;
    payload.model_id = model.id;
  }
  if (values.credentialId !== (agent.model_credential_id ?? "")) {
    payload.model_credential_id = values.credentialId || null;
  }
  if (values.knowledgeCollection !== (agent.knowledge_collection ?? "")) {
    payload.knowledge_collection = values.knowledgeCollection || null;
  }
  if (!sameDependencyFields(values.dependencyFields, agent.dependency_fields)) {
    payload.dependency_fields = values.dependencyFields;
  }
  if (JSON.stringify(values.responseSchema) !== JSON.stringify(agent.response_schema)) {
    payload.response_schema = values.responseSchema;
  }
  const provider = models.find((m) => m.id === values.modelId)?.provider;
  const params = paramsFrom(values, provider);
  if (!sameParams(params, agent.model_params)) payload.model_params = params ?? {};
  const timeout = values.timeoutSeconds.trim() ? Number(values.timeoutSeconds) : null;
  if (timeout !== (agent.timeout_seconds ?? null)) payload.timeout_seconds = timeout;
  // `num_history_runs` e `memory_backend` não existem num agente analista: o
  // backend responde 422 se vierem com valor diferente do padrão.
  if (values.kind !== "analysis") {
    if (values.memoryBackend !== agent.memory_backend) payload.memory_backend = values.memoryBackend;
    if (values.numHistoryRuns !== agent.num_history_runs) payload.num_history_runs = values.numHistoryRuns;
  }
  return payload;
}

interface AgentFormProps {
  mode: "create" | "edit";
  /** Estado salvo (edição) — base para detectar alterações. */
  agent?: AgentDefinition;
  /** Instruções iniciais diferentes das salvas (ex. versão restaurada do histórico). */
  initialInstructions?: string[];
  availableTools: ToolSummary[];
  onSubmit: (payload: AgentFormPayload) => Promise<void>;
  onCancel?: () => void;
  /** `page`: seções em duas colunas com barra de ações fixa; `sheet`: coluna única para painel lateral. */
  variant?: "page" | "sheet";
}

export function AgentForm({
  mode,
  agent,
  initialInstructions,
  availableTools,
  onSubmit,
  onCancel,
  variant = "page",
}: AgentFormProps) {
  const id = useId();
  const [values, setValues] = useState<FormValues>(() => valuesFrom(agent, initialInstructions));
  const [slugTouched, setSlugTouched] = useState(mode === "edit");
  const [showErrors, setShowErrors] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const { modelProviders, modelCredentials, collections } = useWorkspace();
  // `google` sempre disponível (fallback antigo via GOOGLE_API_KEY no ambiente);
  // os demais só entram depois de terem ao menos uma credencial configurada e
  // habilitada em /models.
  const availableProviders = useMemo(
    () => new Set(["google", ...modelCredentials.filter((c) => c.configured && c.enabled).map((c) => c.provider)]),
    [modelCredentials]
  );
  const models = useMemo<ModelOption[]>(() => {
    const base = MODEL_OPTIONS.filter((m) => availableProviders.has(m.provider));
    return agent?.model_id && !base.some((m) => m.id === agent.model_id)
      ? [...base, { provider: agent.model_provider ?? "", id: agent.model_id, label: agent.model_id }]
      : base;
  }, [agent, availableProviders]);

  const currentProvider = models.find((m) => m.id === values.modelId)?.provider;
  const credentialsForProvider = useMemo(
    () => modelCredentials.filter((c) => c.provider === currentProvider && c.enabled),
    [modelCredentials, currentProvider]
  );

  function handleModelChange(modelId: string) {
    const nextProvider = models.find((m) => m.id === modelId)?.provider;
    const keepsCredential = modelCredentials.some(
      (c) => c.id === values.credentialId && c.provider === nextProvider
    );
    setValues((prev) => ({ ...prev, modelId, credentialId: keepsCredential ? prev.credentialId : "" }));
  }

  const instructionLines = toLines(values.instructions);
  const changes = mode === "edit" && agent ? buildUpdate(values, agent, models) : null;
  const dirty = changes
    ? Object.keys(changes).length > 0
    : values.name.trim() !== "" || values.instructions.trim() !== "";

  const errors = {
    name: values.name.trim() ? null : "Dê um nome ao agente.",
    agentType: !values.agentType
      ? "Defina um slug."
      : SLUG_PATTERN.test(values.agentType)
        ? null
        : "Use letras minúsculas, números, '-' ou '_' (começando por letra ou número).",
    instructions: instructionLines.length > 0 ? null : "Escreva ao menos uma instrução.",
    numHistoryRuns: values.numHistoryRuns >= 0 ? null : "Use um número maior ou igual a zero.",
    modelParams:
      numberProblem("temperature", values.temperature) ??
      numberProblem("topP", values.topP) ??
      numberProblem("maxTokens", values.maxTokens) ??
      numberProblem("thinkingBudget", values.thinkingBudget) ??
      numberProblem("timeoutSeconds", values.timeoutSeconds),
    responseSchema:
      values.kind !== "analysis"
        ? null
        : values.responseSchema.length === 0
          ? "Um agente analista precisa de ao menos um campo na saída."
          : schemaProblem(values.responseSchema),
  };
  const hasErrors = Object.values(errors).some(Boolean);

  useEffect(() => {
    if (!dirty || submitting) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty, submitting]);

  function update<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleNameChange(name: string) {
    setValues((prev) => ({ ...prev, name, agentType: slugTouched ? prev.agentType : slugify(name) }));
  }

  function toggleTool(tool: string) {
    update("tools", values.tools.includes(tool) ? values.tools.filter((t) => t !== tool) : [...values.tools, tool]);
  }

  function discard() {
    setValues(valuesFrom(agent));
    setShowErrors(false);
    setSubmitError(null);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setShowErrors(true);
    if (hasErrors || submitting) return;
    if (changes && Object.keys(changes).length === 0) return;

    setSubmitting(true);
    setSubmitError(null);
    try {
      if (changes) {
        await onSubmit(changes);
      } else {
        const model = models.find((m) => m.id === values.modelId) ?? DEFAULT_MODEL;
        const analysis = values.kind === "analysis";
        await onSubmit({
          agent_type: values.agentType,
          name: values.name.trim(),
          kind: values.kind,
          instructions: instructionLines,
          tools: values.tools,
          model_provider: model.provider,
          model_id: model.id,
          model_credential_id: values.credentialId || null,
          knowledge_collection: values.knowledgeCollection || null,
          dependency_fields: values.dependencyFields,
          response_schema: analysis ? values.responseSchema : [],
          model_params: paramsFrom(values, model.provider),
          timeout_seconds: values.timeoutSeconds.trim() ? Number(values.timeoutSeconds) : null,
          // Omitidos em analysis: o backend recusa com 422 um campo que não
          // faz nada num agente one-shot, em vez de aceitá-lo calado.
          ...(analysis
            ? {}
            : { memory_backend: values.memoryBackend, num_history_runs: values.numHistoryRuns }),
        });
      }
      setShowErrors(false);
    } catch (err) {
      setSubmitError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  const fieldError = (key: keyof typeof errors) => (showErrors ? errors[key] : null);
  const promptChanged = Boolean(changes?.instructions);

  const sections = (
    <>
      <FormSection
        variant={variant}
        title="Identidade"
        description="Como o agente aparece no console e como outros módulos o chamam na API."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nome" htmlFor={`${id}-name`} error={fieldError("name")}>
            <Input
              id={`${id}-name`}
              value={values.name}
              onChange={(e) => handleNameChange(e.target.value)}
              placeholder="ex.: Agente de Suporte"
              aria-invalid={Boolean(fieldError("name"))}
              autoFocus={mode === "create"}
            />
          </Field>
          <Field
            label="Slug (agent_type)"
            htmlFor={`${id}-slug`}
            error={fieldError("agentType")}
            hint={mode === "edit" ? "Identificador estável — não pode ser alterado." : "Gerado a partir do nome; usado no campo agent_type da API."}
          >
            <div className="relative">
              <Input
                id={`${id}-slug`}
                value={values.agentType}
                onChange={(e) => {
                  setSlugTouched(true);
                  update("agentType", e.target.value);
                }}
                placeholder="ex.: suporte-nivel-1"
                disabled={mode === "edit"}
                aria-invalid={Boolean(fieldError("agentType"))}
                className={cn("font-mono text-[13px]", mode === "edit" && "pr-10")}
                spellCheck={false}
              />
              {mode === "edit" && (
                <CopyButton value={values.agentType} label="Copiar slug" className="absolute right-1 top-1" />
              )}
            </div>
          </Field>
        </div>
      </FormSection>

      <FormSection
        variant={variant}
        title="Tipo"
        description="Conversacional mantém sessão e histórico e responde texto. Analista é one-shot: recebe um documento e devolve um objeto estruturado."
      >
        <div className="grid gap-2 sm:grid-cols-2">
          {AGENT_KINDS.map(({ kind, label, description }) => {
            const selected = values.kind === kind;
            return (
              <label
                key={kind}
                className={cn(
                  "flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors",
                  selected ? "border-primary bg-primary-soft/50 ring-1 ring-primary" : "border-input hover:bg-accent/50",
                  mode === "edit" && !selected && "cursor-not-allowed opacity-50"
                )}
              >
                <input
                  type="radio"
                  name={`${id}-kind`}
                  value={kind}
                  checked={selected}
                  disabled={mode === "edit"}
                  onChange={() => update("kind", kind)}
                  className="mt-0.5 accent-primary"
                />
                <span className="flex flex-col gap-0.5">
                  <span className="text-[13px] font-medium">{label}</span>
                  <span className="text-xs text-muted-foreground">{description}</span>
                </span>
              </label>
            );
          })}
        </div>
        {mode === "edit" && (
          <p className="mt-2 text-xs text-muted-foreground">
            O tipo não muda depois de criado: ele define o endpoint e o corpo que quem integra usa.
          </p>
        )}
      </FormSection>

      <FormSection
        variant={variant}
        title="Prompt"
        description="Instruções de sistema, uma por linha. Toda alteração salva vira uma nova versão, com histórico e comparação."
      >
        <Field
          label="Instruções"
          htmlFor={`${id}-instructions`}
          error={fieldError("instructions")}
          aside={
            promptChanged && agent ? (
              <Badge variant="warning">será salvo como v{agent.prompt_version + 1}</Badge>
            ) : agent ? (
              <Badge variant="secondary">v{agent.prompt_version}</Badge>
            ) : undefined
          }
          hint={`${formatNumber(instructionLines.length)} ${instructionLines.length === 1 ? "instrução" : "instruções"} · ${formatNumber(values.instructions.length)} caracteres`}
        >
          <Textarea
            id={`${id}-instructions`}
            value={values.instructions}
            onChange={(e) => update("instructions", e.target.value)}
            rows={variant === "sheet" ? 10 : 12}
            placeholder={"Você é um agente de suporte técnico.\nResponda de forma objetiva, em português."}
            aria-invalid={Boolean(fieldError("instructions"))}
            className="min-h-40 resize-y font-mono text-[13px] leading-6"
            spellCheck={false}
          />
        </Field>
      </FormSection>

      <FormSection
        variant={variant}
        title={values.kind === "analysis" ? "Modelo e base" : "Modelo e memória"}
        description={
          values.kind === "analysis"
            ? "Qual LLM analisa o documento e de qual base ele pode consultar."
            : "Qual LLM responde e como o agente lembra do usuário entre mensagens e sessões."
        }
      >
        <div className="flex flex-col gap-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Modelo"
              htmlFor={`${id}-model`}
              hint={
                availableProviders.size <= 1 ? (
                  <Link href="/models" className="hover:underline">
                    Configure outros provedores em Chaves de API
                  </Link>
                ) : undefined
              }
            >
              <Select id={`${id}-model`} value={values.modelId} onChange={(e) => handleModelChange(e.target.value)}>
                {Object.entries(groupByProvider(models, modelProviders)).map(([providerLabel, options]) => (
                  <optgroup key={providerLabel} label={providerLabel}>
                    {options.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </Select>
            </Field>
            {credentialsForProvider.length > 1 && (
              <Field
                label="Chave de API"
                htmlFor={`${id}-credential`}
                hint="Mesmo provedor, chaves diferentes — útil pra separar clientes/times."
              >
                <Select
                  id={`${id}-credential`}
                  value={values.credentialId}
                  onChange={(e) => update("credentialId", e.target.value)}
                >
                  <option value="">Padrão do provedor</option>
                  {credentialsForProvider.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label}
                      {c.key_hint ? ` (${c.key_hint})` : ""}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            <Field
              label="Base de conhecimento"
              htmlFor={`${id}-knowledge`}
              hint={
                collections.length === 0 ? (
                  <Link href="/knowledge" className="hover:underline">
                    Crie uma coleção em Base de conhecimento
                  </Link>
                ) : (
                  "O agente ganha uma busca na coleção e decide sozinho quando consultá-la."
                )
              }
            >
              <Select
                id={`${id}-knowledge`}
                value={values.knowledgeCollection}
                onChange={(e) => update("knowledgeCollection", e.target.value)}
                disabled={collections.length === 0}
              >
                <option value="">Sem base de conhecimento</option>
                {collections.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.label}
                  </option>
                ))}
              </Select>
            </Field>
            {values.kind !== "analysis" && (
              <Field
                label="Execuções no histórico"
                htmlFor={`${id}-history`}
                error={fieldError("numHistoryRuns")}
                hint="Quantas trocas anteriores da sessão entram no contexto."
              >
                <Input
                  id={`${id}-history`}
                  type="number"
                  min={0}
                  value={Number.isNaN(values.numHistoryRuns) ? "" : values.numHistoryRuns}
                  onChange={(e) => update("numHistoryRuns", e.target.valueAsNumber)}
                />
              </Field>
            )}
          </div>
          <Field
            label="Parâmetros de geração"
            error={fieldError("modelParams")}
            hint="Vazio = padrão do provedor. Mudar qualquer um gera uma nova versão da configuração."
          >
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <ParamInput
                id={`${id}-temperature`}
                label="Temperatura"
                placeholder="0–2"
                step="0.1"
                value={values.temperature}
                onChange={(v) => update("temperature", v)}
              />
              <ParamInput
                id={`${id}-top-p`}
                label="top_p"
                placeholder="0–1"
                step="0.05"
                value={values.topP}
                onChange={(v) => update("topP", v)}
              />
              <ParamInput
                id={`${id}-max-tokens`}
                label="Máx. tokens"
                placeholder="padrão"
                value={values.maxTokens}
                onChange={(v) => update("maxTokens", v)}
              />
              {currentProvider === "google" && (
                <ParamInput
                  id={`${id}-thinking`}
                  label="Raciocínio"
                  placeholder="0 = desliga"
                  title="thinking_budget (Gemini 2.5): 0 desliga o raciocínio — mais rápido e barato em decisões simples."
                  value={values.thinkingBudget}
                  onChange={(v) => update("thinkingBudget", v)}
                />
              )}
              <ParamInput
                id={`${id}-timeout`}
                label="Tempo limite (s)"
                placeholder="padrão"
                title="Passou disso, a execução para e a API responde 504 — quem chama cai no próprio fallback."
                value={values.timeoutSeconds}
                onChange={(v) => update("timeoutSeconds", v)}
              />
            </div>
          </Field>
          {values.kind === "analysis" ? (
            <p className="rounded-lg border border-dashed border-border px-4 py-3 text-[13px] text-muted-foreground">
              Um agente analista é one-shot: sem sessão, sem histórico e sem memória de longo prazo. A base de
              conhecimento continua valendo.
            </p>
          ) : (
          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1.5 text-[13px] font-medium">Memória</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {(Object.keys(MEMORY_BACKENDS) as MemoryBackend[]).map((backend) => {
                const selected = values.memoryBackend === backend;
                return (
                  <label
                    key={backend}
                    className={cn(
                      "flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors",
                      selected ? "border-primary bg-primary-soft/50 ring-1 ring-primary" : "border-input hover:bg-accent/50"
                    )}
                  >
                    <input
                      type="radio"
                      name={`${id}-memory`}
                      value={backend}
                      checked={selected}
                      onChange={() => update("memoryBackend", backend)}
                      className="mt-0.5 accent-primary"
                    />
                    <span className="flex flex-col gap-0.5">
                      <span className="text-[13px] font-medium">{MEMORY_BACKENDS[backend].label}</span>
                      <span className="text-xs text-muted-foreground">{MEMORY_BACKENDS[backend].description}</span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>
          )}
        </div>
      </FormSection>

      {values.kind === "analysis" && (
        <FormSection
          variant={variant}
          title="Saída (response_schema)"
          description="A forma do objeto que o /analyze devolve. O modelo é obrigado a preencher exatamente estes campos."
        >
          <Field label="Campos" error={fieldError("responseSchema")}>
            <SchemaFieldsEditor
              value={values.responseSchema}
              onChange={(responseSchema) => update("responseSchema", responseSchema)}
            />
          </Field>
          {values.responseSchema.length === 0 && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="mt-2"
              onClick={() => update("responseSchema", [emptyField()])}
            >
              <Plus className="size-4" /> Começar com um campo
            </Button>
          )}
        </FormSection>
      )}

      <FormSection
        variant={variant}
        title="Campos de contexto (dependencies)"
        description="Quais chaves o agente espera no dependencies do /chat (ex.: cpf) — o que não for declarado aqui continua passando livre, sem validação."
      >
        <DependencyFieldsEditor
          fields={values.dependencyFields}
          onChange={(dependencyFields) => update("dependencyFields", dependencyFields)}
        />
      </FormSection>

      <FormSection
        variant={variant}
        title="Tools"
        description="Funções que o agente pode chamar durante a execução."
        action={
          <Link href="/tools" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
            <Wrench className="size-3" /> Gerenciar tools
          </Link>
        }
      >
        {availableTools.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border px-4 py-3 text-[13px] text-muted-foreground">
            Nenhuma tool criada ainda.{" "}
            <Link href="/tools" className="text-primary hover:underline">
              Crie uma
            </Link>{" "}
            (toolkit padrão do Agno, API ou Python) e ela aparece aqui.
          </p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {availableTools.map((tool) => (
              <label
                key={tool.tool_name}
                title={tool.description ?? undefined}
                className={cn(
                  "flex cursor-pointer items-start gap-2.5 rounded-lg border border-input px-3 py-2 text-[13px] hover:bg-accent/50",
                  !tool.enabled && "opacity-60"
                )}
              >
                <input
                  type="checkbox"
                  checked={values.tools.includes(tool.tool_name)}
                  onChange={() => toggleTool(tool.tool_name)}
                  className="mt-0.5 accent-primary"
                />
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="flex items-center gap-1.5">
                    <span className="truncate font-medium">{tool.label}</span>
                    <Badge variant="outline" className="shrink-0">
                      {TOOL_KIND_META[tool.kind].label}
                    </Badge>
                    {!tool.enabled && (
                      <Badge variant="secondary" className="shrink-0">
                        desativada
                      </Badge>
                    )}
                  </span>
                  <span className="truncate font-mono text-xs text-muted-foreground">{tool.tool_name}</span>
                </span>
              </label>
            ))}
          </div>
        )}
      </FormSection>
    </>
  );

  const status = submitError ? (
    <p className="min-w-0 text-[13px] text-destructive">{submitError}</p>
  ) : mode === "edit" ? (
    <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
      <span className={cn("size-1.5 rounded-full", dirty ? "bg-warning" : "bg-success")} />
      {dirty ? "Alterações não salvas" : "Tudo salvo"}
    </p>
  ) : (
    <span />
  );

  const buttons = (
    <div className="flex shrink-0 items-center gap-2">
      {mode === "edit" && dirty && (
        <Button variant="ghost" onClick={discard} disabled={submitting}>
          Descartar
        </Button>
      )}
      {onCancel && (mode === "create" || variant === "sheet") && (
        <Button variant="outline" onClick={onCancel} disabled={submitting}>
          Cancelar
        </Button>
      )}
      <Button type="submit" disabled={submitting || (mode === "edit" && !dirty)}>
        {submitting && <Spinner />}
        {mode === "create" ? "Criar agente" : "Salvar alterações"}
      </Button>
    </div>
  );

  if (variant === "sheet") {
    return (
      <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col" noValidate>
        <div className="scrollbar-thin flex flex-1 flex-col gap-7 overflow-y-auto px-6 py-5">{sections}</div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-surface px-6 py-3.5">
          {status}
          {buttons}
        </div>
      </form>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col" noValidate>
      <div className="flex flex-col divide-y divide-border">{sections}</div>
      <div className="sticky bottom-0 z-10 -mx-4 mt-2 flex flex-wrap items-center justify-between gap-3 border-t border-border bg-background/90 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
        {status}
        {buttons}
      </div>
    </form>
  );
}

function ParamInput({
  id,
  label,
  value,
  onChange,
  placeholder,
  step,
  title,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  step?: string;
  title?: string;
}) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1 text-xs text-muted-foreground" title={title}>
      {label}
      <Input
        id={id}
        type="number"
        inputMode="decimal"
        step={step ?? "1"}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="h-8"
      />
    </label>
  );
}

function FormSection({
  variant,
  title,
  description,
  action,
  children,
}: {
  variant: "page" | "sheet";
  title: string;
  description: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  if (variant === "sheet") {
    return (
      <section className="flex flex-col gap-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold">{title}</h3>
            <p className="text-xs text-muted-foreground">{description}</p>
          </div>
          {action}
        </div>
        {children}
      </section>
    );
  }
  return (
    <section className="grid gap-4 py-8 first:pt-2 lg:grid-cols-[260px_minmax(0,1fr)] lg:gap-10">
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">{title}</h3>
          {action}
        </div>
        <p className="text-[13px] text-muted-foreground">{description}</p>
      </div>
      <Card className="p-5">{children}</Card>
    </section>
  );
}

function emptyDependencyField(): DependencyField {
  return { name: "", type: "string", label: "", description: "", required: false, default: null };
}

function DependencyFieldsEditor({
  fields,
  onChange,
}: {
  fields: DependencyField[];
  onChange: (fields: DependencyField[]) => void;
}) {
  function updateField(index: number, patch: Partial<DependencyField>) {
    onChange(fields.map((f, i) => (i === index ? { ...f, ...patch } : f)));
  }

  return (
    <div className="flex flex-col gap-3">
      {fields.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">
          Nenhum campo declarado — qualquer <code className="font-mono">dependencies</code> enviado passa sem validação.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {fields.map((f, i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_110px_auto_auto] items-center gap-1.5">
              <Input
                placeholder="nome (ex.: cpf)"
                value={f.name}
                onChange={(e) => updateField(i, { name: e.target.value })}
                className="font-mono text-xs"
              />
              <Input
                placeholder="rótulo (opcional)"
                value={f.label}
                onChange={(e) => updateField(i, { label: e.target.value })}
                className="text-xs"
              />
              <Select value={f.type} onChange={(e) => updateField(i, { type: e.target.value as DependencyFieldType })}>
                {DEPENDENCY_FIELD_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </Select>
              <label className="flex items-center gap-1 text-xs text-muted-foreground" title="Obrigatório">
                <input
                  type="checkbox"
                  checked={f.required}
                  onChange={(e) => updateField(i, { required: e.target.checked })}
                  className="accent-primary"
                />
                obrig.
              </label>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Remover campo"
                onClick={() => onChange(fields.filter((_, idx) => idx !== i))}
              >
                <Trash />
              </Button>
            </div>
          ))}
        </div>
      )}
      <Button variant="outline" size="sm" className="w-fit" onClick={() => onChange([...fields, emptyDependencyField()])}>
        <Plus /> Campo
      </Button>
    </div>
  );
}
