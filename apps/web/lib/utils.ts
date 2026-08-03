import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(n: number | undefined | null) {
  if (n == null) return "—";
  if (!Number.isFinite(n)) return "—";
  // Counts should read as whole numbers; compact from 1,000+
  const rounded = Math.round(n);
  return new Intl.NumberFormat("en", {
    notation: rounded >= 1000 ? "compact" : "standard",
    maximumFractionDigits: rounded >= 1000 ? 1 : 0,
  }).format(rounded);
}

export function formatPct(n: number | undefined | null) {
  if (n == null) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

/** Absolute compact for SPARK leaderboards (always show pts-friendly integers). */
export function formatSparkPts(n: number) {
  return new Intl.NumberFormat("en-IN").format(Math.round(n));
}
