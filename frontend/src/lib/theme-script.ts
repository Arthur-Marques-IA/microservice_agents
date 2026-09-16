export const THEME_STORAGE_KEY = "agent-service:theme";

/**
 * Roda de forma síncrona no <head>, antes do primeiro paint, para a página
 * já nascer no tema certo (sem "flash" claro → escuro). Fica fora do módulo
 * `"use client"` de `theme.ts` porque o root layout (Server Component)
 * precisa da string em si, não de uma referência de client module.
 */
export const themeInitScript = `(function(){try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");var d=t==="dark"||((!t||t==="system")&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.classList.toggle("dark",d)}catch(e){}})()`;
