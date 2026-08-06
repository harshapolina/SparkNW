"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import {
  formatPhase,
  formatScrapeProgress,
  progressPercent,
  type ScrapeProgress,
  type ScrapeStatusItem,
  type ScrapeStatusResponse,
} from "@/lib/scrape-progress";

type BarProps = {
  percent: number;
  className?: string;
  barClassName?: string;
};

export function ScrapeProgressBar({ percent, className, barClassName }: BarProps) {
  const pct = Math.min(100, Math.max(0, percent));
  return (
    <div className={cn("h-2.5 overflow-hidden rounded-full bg-black/50", className)}>
      <div
        className={cn(
          "h-full rounded-full bg-[#ff3b30] transition-all duration-500 ease-out",
          barClassName
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

type CardProps = {
  username?: string;
  progress?: ScrapeProgress | null;
  title?: string;
  className?: string;
  compact?: boolean;
};

/** Clear single-account scrape progress card. */
export function ScrapeProgressCard({
  username,
  progress,
  title,
  className,
  compact,
}: CardProps) {
  const scraped = progress?.scraped_posts ?? 0;
  const total = progress?.total_posts ?? 0;
  const left = progress?.posts_left ?? (total > 0 ? Math.max(0, total - scraped) : 0);
  const pct = progressPercent(progress);
  const phase = formatPhase(progress?.phase);
  const source = progress?.source === "bulk" ? "Bulk queue" : progress?.source === "single" ? "Single refresh" : null;

  return (
    <div
      className={cn(
        "space-y-3 rounded-2xl border border-sky-500/25 bg-sky-500/10 px-4 py-3 text-sky-100",
        className
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-sky-50">
            {title || (username ? `Scraping @${username}` : "Scraping in progress")}
          </div>
          <p className="mt-0.5 text-xs text-sky-200/80">
            {formatScrapeProgress(progress, username)}
          </p>
        </div>
        <div className="text-right">
          <div className="tabular text-lg font-semibold text-white">{pct}%</div>
          {source ? <div className="text-[10px] uppercase tracking-wide text-sky-300/70">{source}</div> : null}
        </div>
      </div>

      <ScrapeProgressBar percent={pct} />

      {!compact ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Phase" value={phase} />
          <Stat label="Scraped" value={scraped.toLocaleString()} />
          <Stat label="Total posts" value={total > 0 ? total.toLocaleString() : "…"} />
          <Stat label="Left" value={total > 0 ? left.toLocaleString() : "…"} />
        </div>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-black/30 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.12em] text-sky-300/60">{label}</div>
      <div className="mt-0.5 text-sm font-medium tabular text-white">{value}</div>
    </div>
  );
}

type ActivityProps = {
  status?: ScrapeStatusResponse | null;
  className?: string;
};

/** Global banner: who is scraping now + queue waiting. */
export function ScrapeActivityBanner({ status, className }: ActivityProps) {
  if (!status || status.active_count <= 0) return null;
  const running = status.running;
  const waiting = status.queue.filter((q) => q.profile_id !== running?.profile_id);

  return (
    <div
      className={cn(
        "space-y-3 rounded-2xl border border-[#ff3b30]/35 bg-[#ff3b30]/10 px-4 py-4",
        className
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-[#ff3b30]">
            Live scrape activity
          </div>
          <p className="mt-1 text-sm text-zinc-200">
            {status.active_count} account{status.active_count === 1 ? "" : "s"} in progress
            {status.pending_bulk > 0 ? ` · ${status.pending_bulk} in bulk queue` : ""}
          </p>
        </div>
      </div>

      {running ? (
        <div className="space-y-2 rounded-xl border border-white/10 bg-black/40 px-3 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <div>
              <span className="font-semibold text-white">Now scraping </span>
              <Link
                href={`/admin-scraping/${running.profile_id}`}
                className="font-semibold text-[#ff3b30] hover:underline"
              >
                @{running.username}
              </Link>
            </div>
            <span className="tabular text-zinc-300">{running.percent}%</span>
          </div>
          <ScrapeProgressBar percent={running.percent} />
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-400">
            <span>
              Posts:{" "}
              <span className="tabular text-zinc-200">
                {running.scraped_posts.toLocaleString()}
                {running.total_posts > 0 ? ` / ${running.total_posts.toLocaleString()}` : ""}
              </span>
            </span>
            <span>
              Left:{" "}
              <span className="tabular text-zinc-200">
                {running.total_posts > 0 ? running.posts_left.toLocaleString() : "…"}
              </span>
            </span>
            <span>Phase: {formatPhase(running.phase)}</span>
            {running.source ? <span>Via: {running.source}</span> : null}
          </div>
        </div>
      ) : (
        <p className="text-sm text-zinc-400">Queued — waiting for the next account to start…</p>
      )}

      {waiting.length > 0 ? (
        <div className="space-y-2">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-500">
            Waiting in queue ({waiting.length})
          </div>
          <ul className="max-h-40 space-y-1.5 overflow-y-auto text-xs text-zinc-400">
            {waiting.slice(0, 12).map((item) => (
              <QueueRow key={item.profile_id} item={item} />
            ))}
            {waiting.length > 12 ? (
              <li className="text-zinc-600">+{waiting.length - 12} more…</li>
            ) : null}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function QueueRow({ item }: { item: ScrapeStatusItem }) {
  return (
    <li className="flex items-center justify-between gap-2 rounded-lg bg-black/30 px-2.5 py-1.5">
      <Link href={`/admin-scraping/${item.profile_id}`} className="hover:text-white">
        @{item.username}
      </Link>
      <span className="tabular text-zinc-500">
        {item.phase || "queued"}
        {item.total_posts > 0
          ? ` · ${item.scraped_posts}/${item.total_posts}`
          : item.scraped_posts > 0
            ? ` · ${item.scraped_posts} posts`
            : ""}
      </span>
    </li>
  );
}

/** Inline row progress for tables. */
export function ScrapeRowProgress({
  username,
  progress,
}: {
  username: string;
  progress?: ScrapeProgress | null;
}) {
  if (!progress?.active) return null;
  const pct = progressPercent(progress);
  const scraped = progress.scraped_posts ?? 0;
  const total = progress.total_posts ?? 0;
  return (
    <div className="mt-2 min-w-[160px] max-w-[220px] space-y-1">
      <div className="flex justify-between gap-2 text-[10px] text-sky-300">
        <span className="truncate">
          {formatPhase(progress.phase)}
          {total > 0 ? ` · ${scraped}/${total}` : scraped > 0 ? ` · ${scraped}` : ""}
        </span>
        <span className="tabular">{pct}%</span>
      </div>
      <ScrapeProgressBar percent={pct} className="h-1.5" />
      <div className="sr-only">{formatScrapeProgress(progress, username)}</div>
    </div>
  );
}
