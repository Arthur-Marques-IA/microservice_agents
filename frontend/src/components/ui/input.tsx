import { InputHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";

export const fieldControlClasses =
  "w-full rounded-lg border border-input bg-card text-sm text-foreground shadow-xs transition-[border-color,box-shadow] " +
  "placeholder:text-muted-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/20 " +
  "disabled:cursor-not-allowed disabled:opacity-60 aria-invalid:border-destructive aria-invalid:ring-destructive/20";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input ref={ref} className={cn(fieldControlClasses, "h-9 px-3", className)} {...props} />
  )
);
Input.displayName = "Input";
