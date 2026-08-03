import { cn } from "@/lib/utils";
import { InputHTMLAttributes, forwardRef } from "react";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-11 w-full rounded-xl border border-border bg-white px-3.5 text-sm text-fg outline-none transition-all duration-200",
        "placeholder:text-slate-400 shadow-soft",
        "hover:border-slate-300",
        "focus:border-accent focus:shadow-glow",
        className
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";
