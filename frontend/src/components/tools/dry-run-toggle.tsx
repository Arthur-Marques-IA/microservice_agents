"use client";

import { useLocalStorage } from "@/lib/use-local-storage";

/**
 * Preferência de "modo teste" do console, uma só para todas as telas que
 * executam tools (Playground, Analisar, testar tool). Ligada por padrão: do
 * console, uma tool com efeito colateral não deveria executar de verdade.
 */
export function useDryRun(): [boolean, (value: boolean) => void] {
  const [pref, setPref] = useLocalStorage<"on" | "off">("agent-service:dry-run", "on");
  return [pref === "on", (value: boolean) => setPref(value ? "on" : "off")];
}

export function DryRunToggle({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex items-start gap-2 text-[13px]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 accent-primary"
      />
      <span>
        <span className="font-medium">Modo teste (dry_run)</span>
        <span className="block text-xs text-muted-foreground">
          As tools recebem <code className="font-mono">X-Kuro-Dry-Run: true</code> e{" "}
          <code className="font-mono">dependencies.dry_run</code>; a API delas decide o que simular. Desligue só para
          executar de verdade.
        </span>
      </span>
    </label>
  );
}
