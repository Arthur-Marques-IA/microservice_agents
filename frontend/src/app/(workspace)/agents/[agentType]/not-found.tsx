import Link from "next/link";
import { Bot } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/primitives";
import { PageBody, PageHeader } from "@/components/workspace/page-header";

export default function AgentNotFound() {
  return (
    <>
      <PageHeader breadcrumbs={[{ label: "Agentes", href: "/agents" }]} title="Agente não encontrado" />
      <PageBody>
        <Card>
          <EmptyState
            icon={Bot}
            title="Esse agente não existe"
            description="Ele pode ter sido excluído, o slug está incorreto ou o agent-service está indisponível."
            action={
              <Link href="/agents" className={buttonVariants({ variant: "outline" })}>
                Ver todos os agentes
              </Link>
            }
          />
        </Card>
      </PageBody>
    </>
  );
}
