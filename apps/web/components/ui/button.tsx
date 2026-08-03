import { cn } from "@/lib/utils";
import { ButtonHTMLAttributes, forwardRef } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "soft";
  size?: "sm" | "md" | "lg";
};

export const Button = forwardRef<HTMLButtonElement, Props>(
  ({ className, variant = "primary", size = "md", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-all duration-200 ease-soft",
          "disabled:opacity-45 disabled:pointer-events-none disabled:shadow-none",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2",
          size === "sm" && "h-8 px-3 text-xs",
          size === "md" && "h-10 px-4 text-sm",
          size === "lg" && "h-11 px-5 text-[15px]",
          variant === "primary" &&
            "bg-accent text-white shadow-soft hover:bg-[#4338CA] hover:shadow-lift hover:-translate-y-px active:translate-y-0",
          variant === "secondary" &&
            "bg-white text-fg border border-border shadow-soft hover:border-slate-300 hover:bg-slate-50 hover:-translate-y-px",
          variant === "soft" && "bg-accent-soft text-accent hover:bg-[#e0e7ff]",
          variant === "ghost" && "bg-transparent text-muted hover:bg-white/80 hover:text-fg",
          variant === "danger" && "bg-danger text-white hover:brightness-110 hover:-translate-y-px",
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
