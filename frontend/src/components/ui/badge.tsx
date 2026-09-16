import { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export type BadgeVariant = "default" | "secondary" | "outline" | "success" | "warning" | "destructive";

const variantClasses: Record<BadgeVariant, string> = {
  default: "bg-primary-soft text-primary",
  secondary: "bg-muted text-muted-foreground",
  outline: "border border-border text-muted-foreground",
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  destructive: "bg-destructive/10 text-destructive",
};

export function Badge({
  className,
  variant = "default",
  ...props
}: HTMLAttributes<HTMLSpanElement> & { variant?: BadgeVariant }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-1.5 text-[11px] font-medium [&_svg]:size-3",
        variantClasses[variant],
        className
      )}
      {...props}
    />
  );
}
