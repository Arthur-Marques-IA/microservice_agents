import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-4 p-6 text-center">
      <p className="font-mono text-sm text-muted-foreground">404</p>
      <h1 className="text-2xl font-semibold tracking-tight">Página não encontrada</h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        O endereço não existe ou mudou. Playground, agentes e base de conhecimento agora ficam no mesmo console.
      </p>
      <Link href="/chat" className={buttonVariants()}>
        Ir para o playground
      </Link>
    </div>
  );
}
