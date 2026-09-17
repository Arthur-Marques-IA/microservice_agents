"use client";

import { useEffect, useState } from "react";

export const PERIODS = [
  { value: "1d", label: "Últimas 24h", days: 1 },
  { value: "7d", label: "Últimos 7 dias", days: 7 },
  { value: "30d", label: "Últimos 30 dias", days: 30 },
  { value: "all", label: "Todo o período", days: null },
] as const;

export type Period = (typeof PERIODS)[number]["value"];

/** `Date.now()` é impuro: calculado num efeito (não durante a renderização) e guardado em estado. */
export function usePeriodSince(period: Period): string | null {
  const [since, setSince] = useState<string | null>(null);
  useEffect(() => {
    const days = PERIODS.find((candidate) => candidate.value === period)?.days;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSince(days ? new Date(Date.now() - days * 86_400_000).toISOString() : null);
  }, [period]);
  return since;
}
