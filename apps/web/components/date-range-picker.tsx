"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { DayPicker, type DateRange } from "react-day-picker";
import { format, startOfDay } from "date-fns";
import { AnimatePresence, motion } from "framer-motion";
import { CalendarDays, ChevronLeft, ChevronRight, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  SPARK_COHORT_START,
  PROGRAMME_STARTED_LABEL,
  clampYmdToCohort,
  defaultCohortRange,
  parseYmdLocal,
  utcTodayYmd,
} from "@/lib/spark/cohort";

type Props = {
  fromDate: string;
  toDate: string;
  onChange: (from: string, to: string) => void;
  onClear: () => void;
  className?: string;
  /** Inclusive earliest selectable day (YYYY-MM-DD). */
  minDate?: string;
  /** Inclusive latest selectable day (YYYY-MM-DD). */
  maxDate?: string;
};

function toYmd(d: Date): string {
  return format(d, "yyyy-MM-dd");
}

function fromYmd(s: string): Date | undefined {
  return parseYmdLocal(s);
}

function labelFor(fromDate: string, toDate: string): string {
  if (fromDate && toDate) {
    const a = fromYmd(fromDate);
    const b = fromYmd(toDate);
    if (a && b) return `${format(a, "d MMM yyyy")} → ${format(b, "d MMM yyyy")}`;
  }
  if (fromDate) {
    const a = fromYmd(fromDate);
    if (a) return `${format(a, "d MMM yyyy")} → …`;
  }
  return "Select date range";
}

/**
 * Single range calendar. Draft selection stays local until both ends are chosen,
 * then commits YYYY-MM-DD to the parent (API). Portaled above filters so campus
 * &lt;select&gt; options cannot steal clicks.
 *
 * Dates are clamped to the SPARK cohort window (default 15 Jul 2026 → today).
 */
export function DateRangePicker({
  fromDate,
  toDate,
  onChange,
  onClear,
  className,
  minDate = SPARK_COHORT_START,
  maxDate,
}: Props) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<DateRange | undefined>();
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const [mounted, setMounted] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  /** First click = start only; second click = end + commit. DayPicker often sets from=to on first click. */
  const phaseRef = useRef<"idle" | "awaiting_end">("idle");

  const todayYmd = utcTodayYmd();
  const floorYmd = minDate || SPARK_COHORT_START;
  const ceilingYmd = maxDate || todayYmd;
  const minDay = startOfDay(fromYmd(floorYmd) || parseYmdLocal(SPARK_COHORT_START)!);
  const maxDay = startOfDay(fromYmd(ceilingYmd) || parseYmdLocal(todayYmd)!);

  const active = Boolean(fromDate && toDate);
  const displayFrom = draft?.from ? toYmd(draft.from) : "";
  const displayTo = draft?.to ? toYmd(draft.to) : "";

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    phaseRef.current = "idle";
    setDraft(
      fromDate && toDate
        ? { from: fromYmd(fromDate), to: fromYmd(toDate) }
        : undefined
    );
  }, [open, fromDate, toDate]);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    function place() {
      const r = triggerRef.current!.getBoundingClientRect();
      const panelW = 320;
      const gap = 8;
      let left = r.left;
      let top = r.bottom + gap;
      if (left + panelW > window.innerWidth - 12) {
        left = Math.max(12, window.innerWidth - panelW - 12);
      }
      const approxH = 420;
      if (top + approxH > window.innerHeight - 12 && r.top > approxH) {
        top = r.top - approxH - gap;
      }
      setPos({ top, left });
    }
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t)) return;
      if (panelRef.current?.contains(t)) return;
      setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function commitRange(from: Date, to: Date) {
    const [a, b] = from.getTime() <= to.getTime() ? [from, to] : [to, from];
    const fromClamped = clampYmdToCohort(toYmd(a), ceilingYmd);
    const toClamped = clampYmdToCohort(toYmd(b), ceilingYmd);
    const fromFinal = fromClamped < floorYmd ? floorYmd : fromClamped;
    const toFinal = toClamped > ceilingYmd ? ceilingYmd : toClamped;
    const [lo, hi] = fromFinal <= toFinal ? [fromFinal, toFinal] : [toFinal, fromFinal];
    setDraft({ from: fromYmd(lo), to: fromYmd(hi) });
    onChange(lo, hi);
    phaseRef.current = "idle";
    setOpen(false);
  }

  function handleSelect(range: DateRange | undefined) {
    if (!range?.from) {
      setDraft(undefined);
      phaseRef.current = "idle";
      return;
    }

    // First click (or restart after a completed range): keep start only — do NOT filter yet.
    if (phaseRef.current === "idle") {
      phaseRef.current = "awaiting_end";
      setDraft({ from: range.from, to: undefined });
      return;
    }

    // Second click: choose end date, then commit.
    const start = draft?.from ?? range.from;
    // Prefer explicit end; if library only moved `from`, use that as end.
    let end = range.to ?? range.from;
    if (toYmd(end) === toYmd(start) && range.from && toYmd(range.from) !== toYmd(start)) {
      end = range.from;
    }
    // Same day as start → stay waiting (user Apply for single-day)
    if (toYmd(end) === toYmd(start)) {
      setDraft({ from: start, to: undefined });
      return;
    }
    commitRange(start, end);
  }

  function applyDraft() {
    if (draft?.from && draft?.to) {
      commitRange(draft.from, draft.to);
      return;
    }
    if (draft?.from) {
      // Explicit single-day only via Apply
      commitRange(draft.from, draft.from);
    }
  }

  function resetToCohort() {
    const def = defaultCohortRange(ceilingYmd);
    phaseRef.current = "idle";
    setDraft({ from: fromYmd(def.from), to: fromYmd(def.to) });
    onChange(def.from, def.to);
    onClear();
    setOpen(false);
  }

  const panel =
    open && mounted
      ? createPortal(
          <AnimatePresence>
            <motion.div
              key="spark-range-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="fixed inset-0 z-[200] bg-black/50 backdrop-blur-[2px]"
              onMouseDown={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setOpen(false);
              }}
            />
            <motion.div
              key="spark-range-panel"
              ref={panelRef}
              initial={{ opacity: 0, y: 10, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.97 }}
              transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
              style={{ top: pos.top, left: pos.left }}
              className="fixed z-[210] w-[min(320px,calc(100vw-24px))]"
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#0e0e0e] shadow-[0_24px_80px_-20px_rgba(0,0,0,0.85)] ring-1 ring-[#ff4d00]/20">
                <div className="flex items-center justify-between border-b border-white/[0.06] bg-gradient-to-r from-[#ff4d00]/15 via-transparent to-transparent px-4 py-3">
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#ff4d00]">
                      Date range
                    </div>
                    <p className="mt-0.5 text-[11px] text-zinc-400">
                      {draft?.from && !draft?.to
                        ? "Now pick the end date"
                        : `From ${floorYmd} → today only`}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="rounded-lg p-1.5 text-zinc-500 hover:bg-white/5 hover:text-white"
                    aria-label="Close"
                  >
                    <X size={14} />
                  </button>
                </div>

                <div className="px-3 pb-2 pt-3">
                  <DayPicker
                    mode="range"
                    selected={draft}
                    onSelect={handleSelect}
                    numberOfMonths={1}
                    defaultMonth={
                      draft?.from || fromYmd(fromDate) || fromYmd(toDate) || minDay
                    }
                    startMonth={minDay}
                    endMonth={maxDay}
                    disabled={{ before: minDay, after: maxDay }}
                    showOutsideDays={false}
                    components={{
                      Chevron: ({ orientation }) =>
                        orientation === "left" ? (
                          <ChevronLeft size={16} className="text-zinc-300" />
                        ) : (
                          <ChevronRight size={16} className="text-zinc-300" />
                        ),
                    }}
                    classNames={{
                      root: "rdp-spark text-zinc-200",
                      months: "flex flex-col",
                      month: "relative space-y-3",
                      month_caption: "relative flex h-9 items-center justify-center px-10",
                      caption_label: "text-sm font-semibold tracking-tight text-zinc-50",
                      nav: "absolute inset-x-0 top-0 flex items-center justify-between",
                      button_previous:
                        "inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-black/50 hover:border-[#ff4d00]/40 hover:bg-[#ff4d00]/10",
                      button_next:
                        "inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-black/50 hover:border-[#ff4d00]/40 hover:bg-[#ff4d00]/10",
                      month_grid: "w-full border-collapse",
                      weekdays: "flex",
                      weekday:
                        "w-10 text-center text-[10px] font-medium uppercase tracking-wider text-zinc-500",
                      week: "mt-1 flex w-full",
                      day: "relative h-10 w-10 p-0 text-center text-sm",
                      day_button:
                        "rdp-day_button inline-flex h-10 w-10 items-center justify-center rounded-full text-zinc-100 transition hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff4d00]/50",
                      selected: "font-semibold text-white",
                      range_start: "rdp-range-start",
                      range_end: "rdp-range-end",
                      range_middle: "rdp-range-middle",
                      today: "font-semibold text-[#ff4d00]",
                      outside: "invisible",
                      disabled: "text-zinc-700 opacity-40",
                      hidden: "invisible",
                    }}
                  />
                </div>

                <div className="flex items-center justify-between gap-2 border-t border-white/[0.06] bg-black/40 px-4 py-3">
                  <div className="min-w-0 text-xs text-zinc-400">
                    <span className="tabular text-zinc-200">
                      {displayFrom && fromYmd(displayFrom)
                        ? format(fromYmd(displayFrom)!, "d MMM")
                        : "Start"}
                    </span>
                    <span className="mx-1.5 text-[#ff4d00]">→</span>
                    <span className="tabular text-zinc-200">
                      {displayTo && fromYmd(displayTo)
                        ? format(fromYmd(displayTo)!, "d MMM")
                        : "End"}
                    </span>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {(draft?.from || active) && (
                      <button
                        type="button"
                        onClick={resetToCohort}
                        className="rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-zinc-400 hover:border-white/20 hover:text-white"
                      >
                        Reset
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={!draft?.from}
                      onClick={applyDraft}
                      className="rounded-lg bg-[#ff4d00] px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                    >
                      Apply
                    </button>
                  </div>
                </div>
              </div>
            </motion.div>
          </AnimatePresence>,
          document.body
        )
      : null;

  return (
    <div className={cn("relative", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <button
          ref={triggerRef}
          type="button"
          onClick={() => {
            // close native selects before opening
            if (document.activeElement instanceof HTMLElement) {
              document.activeElement.blur();
            }
            setOpen((v) => !v);
          }}
          className={cn(
            "inline-flex w-full min-w-0 items-center gap-2.5 rounded-xl border px-3.5 py-2.5 text-left text-sm transition sm:min-w-[260px] sm:w-auto",
            open || active
              ? "border-[#ff4d00]/45 bg-[#ff4d00]/10 text-zinc-100 shadow-[0_0_0_1px_rgba(255,77,0,0.12)]"
              : "border-white/10 bg-black/40 text-zinc-300 hover:border-white/20"
          )}
        >
          <CalendarDays
            size={16}
            className={cn(active || open ? "text-[#ff4d00]" : "text-zinc-500")}
          />
          <span className={cn("flex-1 truncate", !active && "text-zinc-500")}>
            {labelFor(fromDate, toDate)}
          </span>
        </button>
        {active ? (
          <button
            type="button"
            onClick={resetToCohort}
            className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-zinc-300 hover:border-[#ff4d00]/40"
          >
            <X size={14} /> Reset
          </button>
        ) : null}
      </div>
      <p className="mt-1.5 text-[11px] text-zinc-500">
        Dates before {PROGRAMME_STARTED_LABEL} are disabled — data &amp; SPARK points are calculated from programme
        start to the current / selected date.
      </p>
      {panel}
    </div>
  );
}
