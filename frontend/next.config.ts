import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Gera .next/standalone com só o necessário pra rodar em produção —
  // usado pelo Dockerfile pra não precisar copiar node_modules inteiro.
  output: "standalone",
};

export default nextConfig;
