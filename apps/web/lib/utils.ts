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

/** Compact signed integer for follower gain (+1.2K / -50). */
export function formatSignedNumber(n: number | undefined | null) {
  if (n == null || !Number.isFinite(n)) return "—";
  const rounded = Math.round(n);
  const body = new Intl.NumberFormat("en", {
    notation: Math.abs(rounded) >= 1000 ? "compact" : "standard",
    maximumFractionDigits: Math.abs(rounded) >= 1000 ? 1 : 0,
  }).format(Math.abs(rounded));
  if (rounded > 0) return `+${body}`;
  if (rounded < 0) return `−${body}`;
  return body;
}

/** YYYY-MM-DD → short label e.g. 7 Aug */
export function formatBaselineDay(ymd: string | null | undefined) {
  if (!ymd || ymd.length < 10) return null;
  const d = new Date(`${ymd.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return ymd;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

/** Absolute compact for SPARK leaderboards (always show pts-friendly integers). */
export function formatSparkPts(n: number) {
  return new Intl.NumberFormat("en-IN").format(Math.round(n));
}

/** Friendly scrape failure copy for the dashboard (mirrors API humanize). */
export function humanizeScrapeError(raw?: string | null): string {
  if (!raw?.trim()) return "Unknown error — try Refresh to scrape again.";
  const low = raw.toLowerCase();
  if (low.includes("err_tunnel") || low.includes("tunnel_connection")) {
    return "Proxy tunnel failed opening Instagram. Check Decodo credentials, then Refresh.";
  }
  if (low.includes("net::err_") || low.includes("page.goto")) {
    return "Network error reaching Instagram via proxy. Refresh to retry.";
  }
  if (low.includes("login wall") || (low.includes("login") && low.includes("blocked"))) {
    return "Instagram login wall blocked scraping. Verify residential proxy session.";
  }
  if (
    low.includes("does not exist") ||
    low.includes("doesn't exist") ||
    (low.includes("not found") && low.includes("profile"))
  ) {
    return raw.trim();
  }
  if (low.includes("timed out") || low.includes("timeout")) {
    return raw.includes("Refresh")
      ? raw.trim()
      : `${raw.trim()} Raise SCRAPE_JOB_TIMEOUT_SECONDS on the server if proxies are slow.`;
  }
  if (raw.length > 180) return `${raw.slice(0, 177)}…`;
  return raw;
}
