import { Children, ReactElement, ReactNode, isValidElement } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "@/components/ui/code-block";

/*
 * O prompt do Agno pede respostas em markdown, então elas são renderizadas
 * como tal. HTML bruto nunca é interpretado (sem rehype-raw) e o
 * `urlTransform` padrão do react-markdown já neutraliza links `javascript:`.
 */
const components: Components = {
  p: ({ children }) => <p className="my-2.5 first:mt-0 last:mb-0">{children}</p>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2">
      {children}
    </a>
  ),
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  ul: ({ children }) => <ul className="my-2.5 list-disc space-y-1 pl-5 marker:text-muted-foreground">{children}</ul>,
  ol: ({ children }) => <ol className="my-2.5 list-decimal space-y-1 pl-5 marker:text-muted-foreground">{children}</ol>,
  li: ({ children }) => <li className="pl-1">{children}</li>,
  h1: ({ children }) => <h3 className="mb-2 mt-5 text-base font-semibold first:mt-0">{children}</h3>,
  h2: ({ children }) => <h3 className="mb-2 mt-5 text-base font-semibold first:mt-0">{children}</h3>,
  h3: ({ children }) => <h4 className="mb-1.5 mt-4 text-sm font-semibold first:mt-0">{children}</h4>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-border pl-3 text-muted-foreground">{children}</blockquote>
  ),
  hr: () => <hr className="my-4 border-border" />,
  table: ({ children }) => (
    <div className="scrollbar-thin my-3 overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-[13px]">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-b border-border bg-surface px-3 py-2 text-left font-medium">{children}</th>
  ),
  td: ({ children }) => <td className="border-b border-border px-3 py-2 align-top">{children}</td>,
  code: ({ children }) => (
    <code className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[0.85em]">{children}</code>
  ),
  pre: ({ children }) => {
    const child = Children.toArray(children)[0];
    if (!isValidElement(child)) return <pre>{children}</pre>;
    const { className, children: code } = (child as ReactElement<{ className?: string; children?: ReactNode }>)
      .props;
    const language = /language-([\w-]+)/.exec(className ?? "")?.[1];
    return <CodeBlock code={String(code ?? "").replace(/\n$/, "")} title={language} className="my-3" />;
  },
};

export function MessageContent({ content }: { content: string }) {
  return (
    <div className="break-words text-sm leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
