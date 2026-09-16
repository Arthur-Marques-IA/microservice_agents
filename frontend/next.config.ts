import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Gera .next/standalone com só o necessário pra rodar em produção —
  // usado pelo Dockerfile pra não precisar copiar node_modules inteiro.
  output: "standalone",
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
