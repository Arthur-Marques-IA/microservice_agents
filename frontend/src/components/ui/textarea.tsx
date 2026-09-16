import { TextareaHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";
import { fieldControlClasses } from "@/components/ui/input";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea ref={ref} className={cn(fieldControlClasses, "resize-none px-3 py-2", className)} {...props} />
  )
);
Textarea.displayName = "Textarea";
