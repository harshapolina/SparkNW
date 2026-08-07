"use client";

import { cn } from "@/lib/utils";
import { programmeWindowBadge, programmeWindowLine } from "@/lib/spark/cohort";

type Props = {
  /** Optional end date YYYY-MM-DD (defaults to today). */
  toDate?: string | null;
  /** compact = pill only; full = sentence under headings */
  variant?: "full" | "compact";
  className?: string;
};

/** Explains that metrics/points use the SPARK programme window (15 Jul 2026 → current). */
export function ProgrammeWindowNote({ toDate, variant = "full", className }: Props) {
  if (variant === "compact") {
    return (
      <span
        className={cn(
          "inline-flex items-center rounded-full border border-[#ff4d00]/35 bg-[#ff4d00]/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#ff4d00]",
          className
        )}
        title={programmeWindowLine(toDate)}
      >
        {programmeWindowBadge(toDate)}
      </span>
    );
  }

  return (
    <p className={cn("text-sm text-zinc-400", className)}>
      {programmeWindowLine(toDate)}
      <span className="text-zinc-600"> — when the programme started.</span>
    </p>
  );
}
