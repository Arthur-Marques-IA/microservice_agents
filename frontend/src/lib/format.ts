const LOCALE = "pt-BR";

/** Aceita ISO string, Date ou epoch (segundos ou milissegundos — o AgentOS usa os dois). */
export function toDate(value: string | number | Date): Date {
  if (value instanceof Date) return value;
  if (typeof value === "number") return new Date(value < 1e12 ? value * 1000 : value);
  return new Date(value);
}

const relativeFormatter = new Intl.RelativeTimeFormat(LOCALE, { numeric: "auto" });

export function formatRelativeTime(value: string | number | Date, now = Date.now()): string {
  const diffSeconds = Math.round((toDate(value).getTime() - now) / 1000);
  const abs = Math.abs(diffSeconds);
  if (abs < 45) return "agora";
  if (abs < 3600) return relativeFormatter.format(Math.round(diffSeconds / 60), "minute");
  if (abs < 86400) return relativeFormatter.format(Math.round(diffSeconds / 3600), "hour");
  if (abs < 86400 * 7) return relativeFormatter.format(Math.round(diffSeconds / 86400), "day");
  return formatDate(value);
}

export function formatDate(value: string | number | Date): string {
  return new Intl.DateTimeFormat(LOCALE, { day: "2-digit", month: "short", year: "numeric" }).format(
    toDate(value)
  );
}

export function formatDateTime(value: string | number | Date): string {
  return new Intl.DateTimeFormat(LOCALE, { dateStyle: "short", timeStyle: "short" }).format(toDate(value));
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat(LOCALE).format(value);
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${value.toLocaleString(LOCALE, { maximumFractionDigits: 1 })} ${units[unit]}`;
}

export function formatDuration(seconds: number): string {
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  return `${seconds.toLocaleString(LOCALE, { maximumFractionDigits: 1 })} s`;
}


/** Agrupa itens por recência ("Hoje", "Ontem", ...), preservando a ordem de entrada. */
export function groupByRecency<T>(
  items: T[],
  getDate: (item: T) => string | number,
  now = new Date()
): { label: string; items: T[] }[] {
  const day = 86_400_000;
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const buckets = [
    { label: "Hoje", from: startOfToday },
    { label: "Ontem", from: startOfToday - day },
    { label: "Últimos 7 dias", from: startOfToday - 7 * day },
    { label: "Últimos 30 dias", from: startOfToday - 30 * day },
    { label: "Mais antigas", from: -Infinity },
  ];
  const groups = buckets.map((bucket) => ({ label: bucket.label, items: [] as T[] }));
  for (const item of items) {
    const time = toDate(getDate(item)).getTime();
    groups[buckets.findIndex((bucket) => time >= bucket.from)].items.push(item);
  }
  return groups.filter((group) => group.items.length > 0);
}

export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const letters = words.length === 1 ? words[0].slice(0, 2) : words[0][0] + words[1][0];
  return letters.toUpperCase();
}

export function slugify(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

export function pluralize(count: number, singular: string, plural: string): string {
  return `${formatNumber(count)} ${count === 1 ? singular : plural}`;
}
