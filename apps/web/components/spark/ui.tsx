import { cn } from "@/lib/utils";

export function Movement({ delta }: { delta: number }) {
  if (delta > 0) {
    return <span className="text-[11px] font-semibold text-emerald-400">▲ {delta}</span>;
  }
  if (delta < 0) {
    return <span className="text-[11px] font-semibold text-rose-400">▼ {Math.abs(delta)}</span>;
  }
  return <span className="text-[11px] text-zinc-500">—</span>;
}

export function SparkAvatar({
  initials,
  accent,
  size = "md",
}: {
  initials: string;
  accent?: boolean;
  size?: "sm" | "md" | "lg";
}) {
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full font-semibold",
        size === "sm" && "h-8 w-8 text-[10px]",
        size === "md" && "h-9 w-9 text-xs",
        size === "lg" && "h-11 w-11 text-sm",
        accent ? "bg-[#ff3b30] text-white" : "bg-zinc-800 text-zinc-200 ring-1 ring-white/10"
      )}
    >
      {initials.slice(0, 2).toUpperCase()}
    </div>
  );
}

export function ProgressBar({
  value,
  max = 100,
  color = "#ff3b30",
  className,
}: {
  value: number;
  max?: number;
  color?: string;
  className?: string;
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-zinc-800", className)}>
      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

export function LivePill() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-[#ff3b30]/15 px-2.5 py-1 text-[10px] font-bold tracking-[0.14em] text-[#ff3b30]">
      <span className="relative flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#ff3b30] opacity-60" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#ff3b30]" />
      </span>
      LIVE
    </span>
  );
}
