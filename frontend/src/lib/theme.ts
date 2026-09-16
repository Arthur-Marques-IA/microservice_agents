"use client";

import { useCallback, useEffect } from "react";
import { useLocalStorage } from "@/lib/use-local-storage";
import { THEME_STORAGE_KEY } from "@/lib/theme-script";

export type Theme = "light" | "dark" | "system";

function applyTheme(theme: Theme) {
  const dark =
    theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function useTheme(): [Theme, (theme: Theme) => void] {
  const [theme, setStoredTheme] = useLocalStorage<Theme>(THEME_STORAGE_KEY, "system");

  useEffect(() => {
    applyTheme(theme);
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => setStoredTheme(next), [setStoredTheme]);
  return [theme, setTheme];
}
