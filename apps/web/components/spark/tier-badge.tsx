import { cn } from "@/lib/utils";
import type { Tier } from "@/lib/spark/types";

const styles: Record<Tier, string> = {
  GOLD: "border-[#d4a017]/50 text-[#f5c542] bg-[#d4a017]/10",
  SILVER: "border-zinc-400/40 text-zinc-300 bg-zinc-400/10",
  BRONZE: "border-[#c47a3a]/50 text-[#e8a05c] bg-[#c47a3a]/10",
};

export function TierBadge({ tier, className }: { tier: Tier; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 w-[4.25rem] shrink-0 items-center justify-center rounded px-1.5 text-[10px] font-bold tracking-[0.08em]",
        styles[tier],
        className
      )}
    >
      {tier}
    </span>
  );
}
