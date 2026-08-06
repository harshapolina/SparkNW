/** Poll a profile until scrape finishes; reports live scraped/total progress. */

import { api, type Profile } from "@/lib/api";

export type ScrapeProgress = {
  active?: boolean;
  phase?: string;
  scraped_posts?: number;
  total_posts?: number;
  posts_left?: number;
  percent?: number;
  source?: string;
};

export type WaitForScrapeOptions = {
  since?: string | null;
  prevFollowers?: number;
  prevPosts?: number;
  timeoutMs?: number;
  /** Default 5s — avoid hammering the API (and waking proxy use via side effects). */
  intervalMs?: number;
  signal?: AbortSignal;
  onProgress?: (progress: ScrapeProgress | null, profile: Profile) => void;
};

const TERMINAL_PHASES = new Set([
  "done",
  "failed",
  "interrupted",
  "http_posts_only",
]);

function scrapedAfter(profile: Profile, since?: string | null): boolean {
  // Soft-fail / empty attempts used to stamp last_scraped_at with 0 data and
  // make the UI stop waiting as if the scrape succeeded.
  if (!profile.last_scraped_at) return false;
  if ((profile.followers || 0) <= 0 && (profile.posts_count || 0) <= 0) {
    return false;
  }
  if (!since) return true;
  return new Date(profile.last_scraped_at).getTime() > new Date(since).getTime();
}

function scrapeTerminal(profile: Profile, since?: string | null): boolean {
  const prog = profile.scrape_progress;
  const phase = (prog?.phase || "").toLowerCase();

  if (profile.status === "failed" && profile.last_error) {
    return true;
  }

  // Worker finished (success or empty) — stop polling even when counts are 0.
  if (prog && prog.active === false && TERMINAL_PHASES.has(phase)) {
    return true;
  }

  if (scrapedAfter(profile, since)) {
    return true;
  }

  return false;
}

export function formatScrapeProgress(p?: ScrapeProgress | null): string {
  if (!p) return "Scraping…";
  const scraped = p.scraped_posts ?? 0;
  const total = p.total_posts ?? 0;
  const pct = p.percent ?? (total > 0 ? Math.round((100 * scraped) / total) : 0);
  const phase = p.phase || "scraping";
  if (total > 0) {
    return `${phase}: ${scraped}/${total} posts (${pct}%) · ${p.posts_left ?? Math.max(0, total - scraped)} left`;
  }
  return `${phase}: ${scraped} posts scraped…`;
}

export async function waitForProfileScrape(
  profileId: string,
  opts: WaitForScrapeOptions = {}
): Promise<Profile> {
  const timeoutMs = opts.timeoutMs ?? 12 * 60 * 1000;
  const intervalMs = opts.intervalMs ?? 5000;
  const started = Date.now();
  let sawActive = false;

  await new Promise((r) => setTimeout(r, 800));

  while (Date.now() - started < timeoutMs) {
    if (opts.signal?.aborted) throw new Error("Scrape wait cancelled");
    const p = await api<Profile>(`/profiles/${profileId}`);
    opts.onProgress?.(p.scrape_progress || null, p);

    if (p.scrape_progress?.active) {
      sawActive = true;
    }

    if (scrapeTerminal(p, opts.since)) {
      return p;
    }

    // Progress went active → inactive without a terminal phase: treat as finished.
    if (
      sawActive &&
      p.scrape_progress &&
      p.scrape_progress.active === false &&
      (p.last_scraped_at || p.last_error || p.status === "failed")
    ) {
      return p;
    }

    if (
      opts.since &&
      ((opts.prevFollowers != null && p.followers !== opts.prevFollowers) ||
        (opts.prevPosts != null && p.posts_count !== opts.prevPosts)) &&
      (p.followers > 0 || p.posts_count > 0) &&
      !p.scrape_progress?.active
    ) {
      return p;
    }

    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return api<Profile>(`/profiles/${profileId}`);
}
