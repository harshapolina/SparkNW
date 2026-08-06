"""Shared scrape progress display helpers + status types."""

export type ScrapeProgress = {
  active?: boolean;
  phase?: string;
  scraped_posts?: number;
  total_posts?: number;
  posts_left?: number;
  percent?: number;
  source?: string;
  updated_at?: string;
};

export type ScrapeStatusItem = {
  profile_id: string;
  username: string;
  full_name?: string | null;
  source?: string | null;
  phase?: string | null;
  scraped_posts: number;
  total_posts: number;
  posts_left: number;
  percent: number;
  active: boolean;
};

export type ScrapeStatusResponse = {
  running: ScrapeStatusItem | null;
  queue: ScrapeStatusItem[];
  active_count: number;
  pending_bulk: number;
  single_running: number;
};

export function progressPercent(p?: ScrapeProgress | null): number {
  if (!p) return 0;
  if (typeof p.percent === "number" && p.percent > 0) {
    return Math.min(100, Math.max(0, p.percent));
  }
  const scraped = p.scraped_posts ?? 0;
  const total = p.total_posts ?? 0;
  if (total > 0) return Math.min(100, Math.round((100 * scraped) / total));
  return scraped > 0 ? 5 : 0;
}

export function formatPhase(phase?: string | null): string {
  const p = (phase || "scraping").replace(/_/g, " ");
  return p.charAt(0).toUpperCase() + p.slice(1);
}

export function formatScrapeProgress(p?: ScrapeProgress | null, username?: string): string {
  if (!p) return username ? `Scraping @${username}…` : "Scraping…";
  const scraped = p.scraped_posts ?? 0;
  const total = p.total_posts ?? 0;
  const pct = progressPercent(p);
  const left = p.posts_left ?? (total > 0 ? Math.max(0, total - scraped) : 0);
  const who = username ? `@${username} · ` : "";
  const phase = formatPhase(p.phase);
  if (total > 0) {
    return `${who}${phase}: ${scraped.toLocaleString()} / ${total.toLocaleString()} posts (${pct}%) · ${left.toLocaleString()} left`;
  }
  if (scraped > 0) {
    return `${who}${phase}: ${scraped.toLocaleString()} posts scraped…`;
  }
  return `${who}${phase}…`;
}

export function formatScrapeStatusItem(item: ScrapeStatusItem): string {
  return formatScrapeProgress(
    {
      active: item.active,
      phase: item.phase || undefined,
      scraped_posts: item.scraped_posts,
      total_posts: item.total_posts,
      posts_left: item.posts_left,
      percent: item.percent,
      source: item.source || undefined,
    },
    item.username
  );
}
