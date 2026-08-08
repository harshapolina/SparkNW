"use client";

import { cn } from "@/lib/utils";
import {
  isProgrammeWindowLive,
  PROGRAMME_STARTED_LABEL,
  programmeWindowBadge,
  programmeWindowEndLabel,
  programmeWindowLine,
} from "@/lib/spark/cohort";

type Props = {
  /** Optional end date YYYY-MM-DD (defaults to today). */
  toDate?: string | null;
  /** compact = pill only; full = sentence under headings */
  variant?: "full" | "compact";
  className?: string;
};

/** Explains that metrics/points use the SPARK programme window (start → today, live). */
export function ProgrammeWindowNote({ toDate, variant = "full", className }: Props) {
  const endLabel = programmeWindowEndLabel(toDate);
  const live = isProgrammeWindowLive(toDate);

  if (variant === "compact") {
    return (
      <span
        className={cn(
          "inline-flex max-w-full items-center gap-1.5 rounded-full border border-[#ff4d00]/35 bg-[#ff4d00]/10 px-2.5 py-1 text-[10px] font-semibold tracking-[0.06em] text-[#ff4d00]",
          className
        )}
        title={programmeWindowLine(toDate)}
      >
        <span className="uppercase opacity-70">Start</span>
        <span className="uppercase">{PROGRAMME_STARTED_LABEL}</span>
        <span aria-hidden className="opacity-50">
          →
        </span>
        <span className="inline-flex items-center gap-1 uppercase">
          {live ? (
            <>
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]"
                aria-hidden
              />
              <span>Today</span>
              <span className="font-medium normal-case tracking-normal text-[#ff4d00]/90">
                {endLabel}
              </span>
            </>
          ) : (
            <span className="uppercase">{endLabel}</span>
          )}
        </span>
        <span className="sr-only">{programmeWindowBadge(toDate)}</span>
      </span>
    );
  }

  return (
    <p className={cn("text-sm text-zinc-400", className)}>
      {programmeWindowLine(toDate)}
    </p>
  );
}
