import type { NextConfig } from "next";

// Vazio por padrão (dev local, raiz "/"). Em produção o console é servido sob
// um path do mesmo domínio do Regente (ex.: /r8-novo-ui), atrás do Traefik —
// só o build precisa saber disso (basePath vira parte do bundle), por isso
// ARG no Dockerfile em vez de env de runtime.
const basePath = process.env.NEXT_BASE_PATH || "";

const nextConfig: NextConfig = {
  // Gera .next/standalone com só o necessário pra rodar em produção —
  // usado pelo Dockerfile pra não precisar copiar node_modules inteiro.
  output: "standalone",
  ...(basePath ? { basePath } : {}),
  // Rotas antigas (abas separadas) → áreas equivalentes do console unificado.
  async redirects() {
    return [
      { source: "/admin", destination: "/knowledge", permanent: false },
      { source: "/docs", destination: "/agents", permanent: false },
      { source: "/observability", destination: "/logs", permanent: false },
      { source: "/observability/:path*", destination: "/logs/:path*", permanent: false },
    ];
  },
};

export default nextConfig;
