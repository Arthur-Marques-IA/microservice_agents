"use client";

import { Plus, Trash } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { FieldType, ItemType, SchemaField, SchemaItem } from "@/lib/types";

/**
 * Editor de campos compostos, usado em dois lugares: o `response_schema` de um
 * agente analista e os parâmetros `object`/`array` de uma tool. É o mesmo
 * vocabulário nos dois (`field_schema.py` no backend), então duplicar a tela
 * seria duplicar as regras — e elas mudam juntas.
 *
 * As regras que o backend cobra com 422, e que aqui aparecem antes do save:
 * `object` precisa de ao menos um campo, `array` precisa do tipo do item, e
 * um array não tem array dentro.
 */

const FIELD_TYPES: FieldType[] = ["string", "integer", "number", "boolean", "object", "array"];
const ITEM_TYPES: ItemType[] = ["string", "integer", "number", "boolean", "object"];

/** O mesmo teto do backend (`field_schema.MAX_DEPTH`). */
export const MAX_DEPTH = 5;

export function emptyField(): SchemaField {
  return { name: "", type: "string", required: false };
}

/** Primeiro problema que faria o backend recusar o schema, ou `null`. */
export function schemaProblem(fields: SchemaField[], depth = 1): string | null {
  if (depth > MAX_DEPTH) return `campos aninhados demais (máximo ${MAX_DEPTH} níveis)`;
  for (const field of fields) {
    if (!field.name.trim()) return "todo campo precisa de um nome";
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(field.name)) {
      return `nome inválido: ${field.name} (letras, números e _, sem começar com número)`;
    }
    if (field.type === "object") {
      if (!field.fields?.length) return `o campo ${field.name} é object e precisa de ao menos um campo dentro`;
      const dentro = schemaProblem(field.fields, depth + 1);
      if (dentro) return dentro;
    }
    if (field.type === "array") {
      if (!field.items) return `o campo ${field.name} é array e precisa do tipo do item`;
      if (field.items.type === "object") {
        if (!field.items.fields?.length) {
          return `os itens de ${field.name} são object e precisam de ao menos um campo`;
        }
        const dentro = schemaProblem(field.items.fields, depth + 1);
        if (dentro) return dentro;
      }
    }
  }
  return null;
}

export function SchemaFieldsEditor({
  value,
  onChange,
  depth = 1,
  addLabel = "Adicionar campo",
}: {
  value: SchemaField[];
  onChange: (fields: SchemaField[]) => void;
  depth?: number;
  addLabel?: string;
}) {
  function patch(index: number, changes: Partial<SchemaField>) {
    onChange(value.map((field, i) => (i === index ? normalize({ ...field, ...changes }) : field)));
  }

  return (
    <div className="flex flex-col gap-2">
      {value.map((field, index) => (
        <div key={index} className="rounded-lg border border-border bg-muted/30 p-2">
          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={field.name}
              onChange={(e) => patch(index, { name: e.target.value })}
              placeholder="nome"
              className="h-8 w-40"
              aria-label="Nome do campo"
            />
            <Select
              value={field.type}
              onChange={(e) => patch(index, { type: e.target.value as FieldType })}
              className="h-8 w-32"
              aria-label="Tipo do campo"
            >
              {FIELD_TYPES.map((t) => (
                <option key={t} value={t} disabled={t === "array" && depth >= MAX_DEPTH}>
                  {t}
                </option>
              ))}
            </Select>
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={Boolean(field.required)}
                onChange={(e) => patch(index, { required: e.target.checked })}
              />
              obrigatório
            </label>
            <Input
              value={field.description ?? ""}
              onChange={(e) => patch(index, { description: e.target.value })}
              placeholder="descrição (ajuda o modelo a preencher)"
              className="h-8 min-w-40 flex-1"
              aria-label="Descrição do campo"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => onChange(value.filter((_, i) => i !== index))}
              aria-label={`Remover ${field.name || "campo"}`}
            >
              <Trash className="size-4" />
            </Button>
          </div>

          {field.type === "object" && (
            <Nested title="campos de dentro" depth={depth}>
              <SchemaFieldsEditor
                value={field.fields ?? []}
                onChange={(fields) => patch(index, { fields })}
                depth={depth + 1}
              />
            </Nested>
          )}

          {field.type === "array" && (
            <Nested title="cada item é" depth={depth}>
              <ItemEditor
                value={field.items ?? { type: "string" }}
                onChange={(items) => patch(index, { items })}
                depth={depth}
              />
            </Nested>
          )}
        </div>
      ))}
      <div>
        <Button type="button" variant="outline" size="sm" onClick={() => onChange([...value, emptyField()])}>
          <Plus className="size-4" /> {addLabel}
        </Button>
      </div>
    </div>
  );
}

function ItemEditor({
  value,
  onChange,
  depth,
}: {
  value: SchemaItem;
  onChange: (item: SchemaItem) => void;
  depth: number;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Select
        value={value.type}
        onChange={(e) => {
          const type = e.target.value as ItemType;
          onChange(type === "object" ? { type, fields: value.fields ?? [emptyField()] } : { type });
        }}
        className="h-8 w-32"
        aria-label="Tipo do item"
      >
        {ITEM_TYPES.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </Select>
      {value.type === "object" && (
        <SchemaFieldsEditor
          value={value.fields ?? []}
          onChange={(fields) => onChange({ ...value, fields })}
          depth={depth + 1}
        />
      )}
    </div>
  );
}

function Nested({ title, depth, children }: { title: string; depth: number; children: React.ReactNode }) {
  if (depth >= MAX_DEPTH) {
    return (
      <p className="mt-2 border-l-2 border-border pl-3 text-xs text-destructive">
        limite de {MAX_DEPTH} níveis de aninhamento — o provedor recusa schemas mais fundos.
      </p>
    );
  }
  return (
    <div className="mt-2 border-l-2 border-border pl-3">
      <p className="mb-1.5 text-xs text-muted-foreground">{title}</p>
      {children}
    </div>
  );
}

/** Troca de tipo não deixa para trás o `fields`/`items` do tipo anterior — o
 * backend recusa um `string` que veio com `fields`. */
function normalize(field: SchemaField): SchemaField {
  if (field.type === "object") {
    return { ...field, items: undefined, fields: field.fields?.length ? field.fields : [emptyField()] };
  }
  if (field.type === "array") {
    return { ...field, fields: undefined, items: field.items ?? { type: "string" } };
  }
  return { ...field, fields: undefined, items: undefined };
}
