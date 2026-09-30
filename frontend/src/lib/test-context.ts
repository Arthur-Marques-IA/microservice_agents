import type { DependencyField } from "@/lib/types";

/**
 * Valores de teste para o `dependencies` do Playground.
 *
 * Tudo aqui é fictício de propósito: um telefone com DDD 00, e-mail `.invalid`,
 * CPF zerado — nenhum deles alcança um cliente real se o agente (ou uma tool)
 * os repassar a um sistema externo. Identificadores de conversa levam o prefixo
 * `teste-` e nascem do id da sessão, então cada conversa nova tem o seu e um
 * teste não se emenda no histórico de outro.
 */

const PREFIX = "teste";

const BY_NAME: { match: RegExp; value: string }[] = [
  { match: /(telefone|celular|fone|phone|whats|mobile)/i, value: "5500000000000" },
  { match: /e-?mail/i, value: "teste@example.invalid" },
  { match: /cnpj/i, value: "00.000.000/0000-00" },
  { match: /(cpf|documento)/i, value: "000.000.000-00" },
  { match: /(nome|name)/i, value: "Cliente de Teste" },
  { match: /(cep)/i, value: "00000-000" },
];

const ID_LIKE = /(^id$|_id$|id_|conversation|conversa|session|sessao|sessão|lead|ticket|protocolo|thread)/i;

function valueFor(field: DependencyField, seed: string): unknown {
  if (field.default !== null && field.default !== undefined && field.default !== "") return field.default;
  if (field.enum && field.enum.length > 0) return field.enum[0];

  switch (field.type) {
    case "boolean":
      return false;
    case "integer":
    case "number":
      // Um id numérico positivo poderia cair num registro real.
      return ID_LIKE.test(field.name) ? -1 : 0;
    default: {
      if (ID_LIKE.test(field.name)) return `${PREFIX}-${seed.slice(0, 8)}`;
      const named = BY_NAME.find((entry) => entry.match.test(field.name));
      return named ? named.value : `${PREFIX}-${field.name}`;
    }
  }
}

/** Objeto com todos os campos declarados (obrigatórios e opcionais). `seed` = id da conversa. */
export function buildTestDependencies(fields: DependencyField[], seed: string): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of fields) result[field.name] = valueFor(field, seed);
  return result;
}

/** O mesmo objeto como JSON indentado, ou `""` se o agente não declara campos. */
export function testDependenciesText(fields: DependencyField[] | undefined, seed: string): string {
  if (!fields || fields.length === 0 || !seed) return "";
  return JSON.stringify(buildTestDependencies(fields, seed), null, 2);
}
