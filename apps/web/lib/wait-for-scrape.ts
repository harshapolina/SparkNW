/** Poll a profile until scrape finishes (queued Add/Refresh returns immediately). */

import { api, type Profile } from "@/lib/api";

export type WaitForScrapeOptions = {
  /** Baseline last_scraped_at before queueing (ISO string or null). */
  since?: string | null;
  /** Previous followers count — used when last_scraped_at was already set. */
  prevFollowers?: number;
  prevPosts?: number;
  /** Max wait in ms (default 12 minutes). */
  timeoutMs?: number;
  /** Poll interval in ms (default 3s). */
  intervalMs?: number;
  signal?: AbortSignal;
};

function scrapedAfter(profile: Profile, since?: string | null): boolean {
  if (!profile.last_scraped_at) return false;
  if (!since) return true;
  return new Date(profile.last_scraped_at).getTime() > new Date(since).getTime();
}

export async function waitForProfileScrape(
  profileId: string,
  opts: WaitForScrapeOptions = {}
): Promise<Profile> {
  const timeoutMs = opts.timeoutMs ?? 12 * 60 * 1000;
  const intervalMs = opts.intervalMs ?? 3000;
  const started = Date.now();

  // Give the worker a moment to pick up the job.
  await new Promise((r) => setTimeout(r, 800));

  while (Date.now() - started < timeoutMs) {
    if (opts.signal?.aborted) throw new Error("Scrape wait cancelled");
    const p = await api<Profile>(`/profiles/${profileId}`);
    if (p.status === "failed" && p.last_error) {
      return p;
    }
    if (scrapedAfter(p, opts.since)) {
      return p;
    }
    // Fallback: metrics moved even if timestamp edge-case
    if (
      opts.since &&
      ((opts.prevFollowers != null && p.followers !== opts.prevFollowers) ||
        (opts.prevPosts != null && p.posts_count !== opts.prevPosts)) &&
      (p.followers > 0 || p.posts_count > 0)
    ) {
      return p;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  // Final read — return whatever we have (may still be scraping).
  return api<Profile>(`/profiles/${profileId}`);
}
