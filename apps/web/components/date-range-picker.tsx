"use client";

import { useEffect, useRef, useState } from "react";
import { DayPicker, type DateRange } from "react-day-picker";
import { format, parseISO } from "date-fns";
import { AnimatePresence, motion } from "framer-motion";
import { CalendarDays, ChevronLeft, ChevronRight, X } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  fromDate: string;
  toDate: string;
  onChange: (from: string, to: string) => void;
  onClear: () => void;
  className?: string;
};

function toYmd(d: Date): string {
  return format(d, "yyyy-MM-dd");
}

function fromYmd(s: string): Date | undefined {
  if (!s) return undefined;
  const d = parseISO(s);
  return Number.isNaN(d.getTime()) ? undefined : d;
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

/** Single aesthetic range calendar — keeps YYYY-MM-DD strings for API callers. */
export function DateRangePicker({ fromDate, toDate, onChange, onClear, className }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const selected: DateRange | undefined = fromDate
    ? {
        from: fromYmd(fromDate),
        to: toDate ? fromYmd(toDate) : undefined,
      }
    : undefined;

  const active = Boolean(fromDate || toDate);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function handleSelect(range: DateRange | undefined) {
    if (!range?.from) {
      onChange("", "");
      return;
    }
    const from = toYmd(range.from);
    const to = range.to ? toYmd(range.to) : "";
    onChange(from, to);
    if (range.from && range.to) setOpen(false);
  }

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className={cn(
            "inline-flex min-w-[240px] items-center gap-2.5 rounded-xl border px-3.5 py-2.5 text-left text-sm transition",
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
            onClick={() => {
              onClear();
              setOpen(false);
            }}
            className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-zinc-300 hover:border-[#ff4d00]/40"
          >
            <X size={14} /> Clear
          </button>
        ) : null}
      </div>

      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.98 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="absolute left-0 z-40 mt-2 origin-top-left"
          >
            <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#121212] p-3 shadow-2xl shadow-black/50 ring-1 ring-[#ff4d00]/15">
              <div className="mb-2 flex items-center justify-between px-1">
                <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#ff4d00]">
                  Date range
                </div>
                <p className="text-[11px] text-zinc-500">
                  {fromDate && !toDate ? "Pick end date" : "Click start, then end"}
                </p>
              </div>

              <DayPicker
                mode="range"
                selected={selected}
                onSelect={handleSelect}
                numberOfMonths={1}
                defaultMonth={fromYmd(fromDate) || fromYmd(toDate) || new Date()}
                showOutsideDays
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
                  caption_label: "text-sm font-semibold tracking-tight text-zinc-100",
                  nav: "absolute inset-x-0 top-0 flex items-center justify-between",
                  button_previous:
                    "inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-black/40 hover:border-[#ff4d00]/40 hover:bg-[#ff4d00]/10",
                  button_next:
                    "inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-black/40 hover:border-[#ff4d00]/40 hover:bg-[#ff4d00]/10",
                  month_grid: "w-full border-collapse",
                  weekdays: "flex",
                  weekday: "w-9 text-center text-[10px] font-medium uppercase tracking-wider text-zinc-500",
                  week: "mt-1 flex w-full",
                  day: "relative h-9 w-9 p-0 text-center text-sm",
                  day_button:
                    "rdp-day_button inline-flex h-9 w-9 items-center justify-center rounded-full text-zinc-200 transition hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff4d00]/50",
                  selected: "font-semibold text-white",
                  range_start: "rdp-range-start",
                  range_end: "rdp-range-end",
                  range_middle: "rdp-range-middle",
                  today: "font-semibold text-[#ff4d00]",
                  outside: "text-zinc-600 opacity-50",
                  disabled: "text-zinc-700 opacity-40",
                  hidden: "invisible",
                }}
              />

              <div className="mt-3 flex items-center justify-between border-t border-white/[0.06] px-1 pt-3 text-[11px] text-zinc-500">
                <span>
                  {fromDate ? format(fromYmd(fromDate)!, "d MMM") : "—"}
                  <span className="mx-1.5 text-[#ff4d00]">→</span>
                  {toDate ? format(fromYmd(toDate)!, "d MMM") : "—"}
                </span>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="rounded-lg px-2 py-1 text-zinc-400 hover:bg-white/5 hover:text-white"
                >
                  Done
                </button>
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
