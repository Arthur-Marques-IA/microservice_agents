"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";

const links = [
  { href: "/chat", label: "Chat" },
  { href: "/admin", label: "Admin" },
];

export function Nav() {
  const pathname = usePathname();

  return (
    <header className="border-b border-border">
      <nav className="mx-auto flex h-14 max-w-5xl items-center gap-6 px-4">
        <span className="text-sm font-semibold">agent-service</span>
        <div className="flex gap-1">
          {links.map((link) => {
            const active = pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted"
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </header>
  );
}
