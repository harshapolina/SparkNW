import { cn } from "@/lib/utils";

export function Card({
  className,
  children,
  hover = false,
  padding = "md",
  onClick,
}: {
  className?: string;
  children: React.ReactNode;
  hover?: boolean;
  padding?: "none" | "sm" | "md" | "lg";
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "rounded-[22px] border border-stone-200/60 bg-white shadow-card",
        hover && "transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lift",
        onClick && "cursor-pointer",
        padding === "none" && "p-0",
        padding === "sm" && "p-4",
        padding === "md" && "p-5",
        padding === "lg" && "p-6 md:p-7",
        className
      )}
    >
      {children}
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.14em] text-stone-400">{eyebrow}</div>}
        <h1 className="page-title">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-[15px] leading-relaxed text-stone-500">{description}</p>}
      </div>
      {action && <div className="flex shrink-0 flex-wrap items-center gap-2">{action}</div>}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-[22px] border border-dashed border-stone-300 bg-white/50 px-6 py-16 text-center">
      <div className="mb-3 h-10 w-10 rounded-full bg-[#ede9fe]" />
      <h3 className="font-[family-name:var(--font-display)] text-lg font-semibold tracking-tight">{title}</h3>
      <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-stone-500">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
