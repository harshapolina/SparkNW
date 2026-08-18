"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  Clock,
  Eye,
  Film,
  RefreshCw,
  Users,
  Video,
} from "lucide-react";
import { api } from "@/lib/api";
import type { AdminOverviewResponse } from "@/lib/spark/api-types";
import { cn, formatNumber } from "@/lib/utils";
import { SparkAvatar } from "@/components/spark/ui";
import { ProgrammeWindowNote } from "@/components/programme-window-note";
import { CampusUploadsTable } from "@/components/campus-uploads-table";

type YtSyncStatus = {
  active_count: number;
  queue: { profile_id: string; username: string; status: string }[];
  history: { profile_id: string; username: string; status?: string; finished_at?: string | null }[];
  connected_total: number;
  scraped_total?: number;
  not_scraped_total?: number;
  board_total?: number;
};

function Metric({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "good" | "warn" | "bad";
}) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
      <div className="text-[11px] uppercase tracking-[0.1em] text-zinc-500">{label}</div>
      <div
        className={cn(
          "mt-3 text-2xl font-semibold tabular tracking-tight",
          tone === "good" && "text-lime-400",
          tone === "warn" && "text-amber-300",
          tone === "bad" && "text-rose-400"
        )}
      >
        {value}
      </div>
      {hint ? <div className="mt-1 text-[11px] text-zinc-500">{hint}</div> : null}
    </div>
  );
}

export function AdminYouTubeDashboard({ admin }: { admin: AdminOverviewResponse }) {
  const yt = admin.youtube;
  const syncQ = useQuery({
    queryKey: ["youtube", "sync-status"],
    queryFn: () => api<YtSyncStatus>("/youtube/sync-status"),
    refetchInterval: (q) => ((q.state.data?.active_count || 0) > 0 ? 3000 : 20000),
  });

  const live = syncQ.data;
  const connected = live?.connected_total ?? yt?.connected ?? 0;
  const scraped = live?.scraped_total ?? yt?.scraped ?? 0;
  const notScraped =
    live?.not_scraped_total ?? yt?.not_scraped ?? Math.max(0, connected - scraped);
  const roster = admin.total_participants || admin.overall?.total_profiles || 0;
  const coverage = connected ? Math.round((scraped / connected) * 1000) / 10 : 0;
  const connectPct = roster ? Math.round((connected / roster) * 1000) / 10 : 0;
  const top = yt?.top_channels || [];
  const queue = syncQ.data?.queue || [];
  const history = syncQ.data?.history || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-[0.14em] text-zinc-500">{admin.week_label}</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">YouTube intelligence</h1>
          <ProgrammeWindowNote
            className="mt-1"
            toDate={admin.date_range?.split("→").pop()?.trim() || admin.today?.date}
          />
          <p className="mt-1 max-w-2xl text-sm text-zinc-500">
            Channel coverage, sync health, and top creators — separate from Instagram scrapes.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/admin-scraping/youtube"
            className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-white/10 bg-[#121212] px-3 text-xs text-zinc-300 hover:border-[#ff4d00]/40"
          >
            <RefreshCw size={13} /> YouTube board
          </Link>
          <Link
            href="/admin-settings"
            className="inline-flex h-9 items-center rounded-xl border border-white/10 bg-[#121212] px-3 text-xs text-zinc-300 hover:border-[#ff4d00]/40"
          >
            Sync settings
          </Link>
        </div>
      </div>

      {/* Coverage strip */}
      <div className="overflow-hidden rounded-2xl border border-white/[0.06] bg-[#121212]">
        <div className="grid gap-0 lg:grid-cols-[1.2fr_1fr]">
          <div className="border-b border-white/[0.06] p-5 lg:border-b-0 lg:border-r">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-zinc-500">
              <Video size={14} className="text-[#ff3b30]" /> Sync coverage
            </div>
            <div className="mt-4 flex items-end gap-6">
              <div>
                <div className="text-4xl font-semibold tabular tracking-tight text-lime-400">
                  {coverage}%
                </div>
                <div className="mt-1 text-xs text-zinc-500">
                  {formatNumber(scraped)} of {formatNumber(connected)} connected channels scraped
                </div>
              </div>
              <div className="pb-1">
                <div className="text-2xl font-semibold tabular text-zinc-200">{connectPct}%</div>
                <div className="mt-1 text-xs text-zinc-500">
                  {formatNumber(connected)} / {formatNumber(roster)} roster connected
                </div>
              </div>
            </div>
            <div className="mt-5 h-2 overflow-hidden rounded-full bg-black/60">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[#ff3b30] to-lime-400"
                style={{ width: `${Math.min(100, coverage)}%` }}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-px bg-white/[0.04]">
            {[
              {
                label: "Daily sync",
                value: yt?.daily_sync_enabled ? "ON" : "OFF",
                tone: yt?.daily_sync_enabled ? "text-lime-400" : "text-zinc-400",
              },
              {
                label: "In queue",
                value: formatNumber(syncQ.data?.active_count || 0),
                tone: "text-sky-300",
              },
              {
                label: "Failed / unavailable",
                value: formatNumber(yt?.failed ?? 0),
                tone: (yt?.failed ?? 0) > 0 ? "text-rose-400" : "text-zinc-300",
              },
              {
                label: "Quota blocked",
                value: formatNumber(yt?.quota_exceeded ?? 0),
                tone: (yt?.quota_exceeded ?? 0) > 0 ? "text-amber-300" : "text-zinc-300",
              },
            ].map((cell) => (
              <div key={cell.label} className="bg-[#121212] p-4">
                <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">{cell.label}</div>
                <div className={cn("mt-2 text-xl font-semibold tabular", cell.tone)}>{cell.value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <CampusUploadsTable platform="youtube" />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Subscribers"
          value={formatNumber(yt?.total_subscribers ?? 0)}
          hint={`Avg ${formatNumber(yt?.avg_subscribers ?? 0)} per connected channel`}
          tone="good"
        />
        <Metric label="Lifetime views" value={formatNumber(yt?.total_views ?? 0)} hint="Sum across connected channels" />
        <Metric label="Videos tracked" value={formatNumber(yt?.total_videos ?? 0)} hint="Public channel video counts" />
        <Metric
          label="Not scraped yet"
          value={formatNumber(notScraped)}
          hint={`${formatNumber(yt?.no_youtube ?? 0)} roster rows have no YouTube link`}
          tone={notScraped > 0 ? "warn" : "default"}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr] xl:items-stretch">
        <div className="flex min-h-0 flex-col rounded-2xl border border-white/[0.06] bg-[#121212] p-5 xl:h-[520px]">
          <div className="mb-4 flex shrink-0 items-end justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">Top channels</h2>
              <p className="mt-0.5 text-xs text-zinc-500">By subscriber count among connected creators</p>
            </div>
            <Link href="/admin-scraping/youtube" className="text-xs text-[#ff3b30] hover:underline">
              Full board →
            </Link>
          </div>
          {!top.length ? (
            <p className="py-10 text-center text-sm text-zinc-500">
              No connected channels yet. Import YouTube links or connect from a creator page.
            </p>
          ) : (
            <div className="thin-scroll min-h-0 flex-1 overflow-y-auto">
              <table className="w-full table-fixed text-left text-sm">
                <colgroup>
                  <col className="w-10" />
                  <col />
                  <col className="w-[18%]" />
                  <col className="w-[16%]" />
                  <col className="w-[14%]" />
                  <col className="w-[16%]" />
                </colgroup>
                <thead className="sticky top-0 bg-[#121212]">
                  <tr className="border-b border-white/[0.06] text-[10px] uppercase tracking-[0.12em] text-zinc-500">
                    <th className="px-2 py-2">#</th>
                    <th className="px-2 py-2">Creator</th>
                    <th className="px-2 py-2 text-right">Subs</th>
                    <th className="px-2 py-2 text-right">Views</th>
                    <th className="px-2 py-2 text-right">Videos</th>
                    <th className="px-2 py-2 text-right">Synced</th>
                  </tr>
                </thead>
                <tbody>
                  {top.map((row, idx) => (
                    <tr key={row.profile_id} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                      <td className="px-2 py-3 tabular text-zinc-600">{idx + 1}</td>
                      <td className="px-2 py-3">
                        <Link
                          href={`/admin-scraping/${row.profile_id}`}
                          className="flex min-w-0 items-center gap-2.5 hover:opacity-90"
                        >
                          <SparkAvatar
                            initials={(row.full_name || row.username || "?")
                              .slice(0, 2)
                              .toUpperCase()}
                            size="sm"
                          />
                          <div className="min-w-0">
                            <div className="truncate font-medium">{row.full_name || row.username}</div>
                            <div className="truncate text-[11px] text-zinc-500">
                              {row.channel_name || row.handle || `@${row.username}`}
                            </div>
                          </div>
                        </Link>
                      </td>
                      <td className="px-2 py-3 text-right tabular">
                        {row.hidden_subscribers ? "Hidden" : formatNumber(row.subscribers)}
                      </td>
                      <td className="px-2 py-3 text-right tabular text-zinc-300">
                        {formatNumber(row.views)}
                      </td>
                      <td className="px-2 py-3 text-right tabular text-zinc-300">
                        {formatNumber(row.videos)}
                      </td>
                      <td className="px-2 py-3 text-right text-[11px] text-zinc-500">
                        {row.last_synced_at
                          ? new Date(row.last_synced_at).toLocaleString(undefined, {
                              day: "2-digit",
                              month: "short",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="flex min-h-0 flex-col gap-4 xl:h-[520px]">
          <div className="flex shrink-0 flex-col rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold">Live sync queue</h2>
              <span className="inline-flex items-center gap-1 text-[11px] text-zinc-500">
                <Activity size={12} className="text-sky-400" />
                {syncQ.data?.active_count || 0} active
              </span>
            </div>
            <div className="thin-scroll h-[88px] overflow-y-auto">
              {!queue.length ? (
                <p className="text-sm text-zinc-500">
                  Queue is clear. Daily 08:00 IST runs when sync is ON.
                </p>
              ) : (
                <ul className="space-y-2 text-xs">
                  {queue.map((row) => (
                    <li
                      key={`${row.profile_id}-${row.status}`}
                      className="flex items-center justify-between gap-2 rounded-xl border border-white/[0.05] bg-black/30 px-3 py-2"
                    >
                      <Link
                        href={`/admin-scraping/${row.profile_id}`}
                        className="font-medium hover:text-[#ff4d00]"
                      >
                        @{row.username}
                      </Link>
                      <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] uppercase text-sky-300">
                        {row.status}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <dl className="mt-3 space-y-2 border-t border-white/[0.05] pt-3 text-xs">
              <div className="flex justify-between gap-3">
                <dt className="text-zinc-500">Last sync</dt>
                <dd>{yt?.last_sync ? new Date(yt.last_sync).toLocaleString() : "—"}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-zinc-500">Next</dt>
                <dd className="text-right text-zinc-300">{yt?.next_sync || "—"}</dd>
              </div>
            </dl>
          </div>

          <div className="shrink-0 rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
            <h2 className="text-sm font-semibold">Why channels aren’t scraped</h2>
            <ul className="mt-4 space-y-3 text-sm">
              <li className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 text-zinc-300">
                  <BadgeCheck size={14} className="text-lime-400" /> Scraped successfully
                </span>
                <span className="font-semibold tabular">{formatNumber(scraped)}</span>
              </li>
              <li className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 text-zinc-300">
                  <Clock size={14} className="text-amber-300" /> Connected, waiting sync
                </span>
                <span className="font-semibold tabular">
                  {formatNumber(yt?.pending_sync ?? notScraped)}
                </span>
              </li>
              <li className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 text-zinc-300">
                  <AlertTriangle size={14} className="text-rose-400" /> Failed / quota
                </span>
                <span className="font-semibold tabular text-rose-300">
                  {formatNumber((yt?.failed ?? 0) + (yt?.quota_exceeded ?? 0))}
                </span>
              </li>
              <li className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 text-zinc-300">
                  <Users size={14} className="text-zinc-500" /> No YouTube on roster
                </span>
                <span className="font-semibold tabular">{formatNumber(yt?.no_youtube ?? 0)}</span>
              </li>
            </ul>
          </div>

          <div className="flex min-h-0 flex-1 flex-col rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
            <h2 className="mb-3 shrink-0 text-sm font-semibold">Recent syncs</h2>
            <div className="thin-scroll min-h-0 flex-1 overflow-y-auto">
              {!history.length ? (
                <p className="text-sm text-zinc-500">No completed YouTube jobs yet.</p>
              ) : (
                <ul className="space-y-2 text-xs">
                  {history.map((row, i) => (
                    <li
                      key={`${row.profile_id}-${row.finished_at || i}`}
                      className="flex items-center justify-between gap-2 border-b border-white/[0.04] pb-2 last:border-0"
                    >
                      <Link
                        href={`/admin-scraping/${row.profile_id}`}
                        className="font-medium hover:text-[#ff4d00]"
                      >
                        @{row.username}
                      </Link>
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] uppercase",
                          row.status === "success"
                            ? "bg-lime-500/15 text-lime-400"
                            : "bg-rose-500/15 text-rose-300"
                        )}
                      >
                        {row.status || "—"}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Link
          href="/admin-scraping/youtube"
          className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4 transition hover:border-[#ff3b30]/40"
        >
          <Film size={16} className="text-[#ff3b30]" />
          <div className="mt-3 text-sm font-semibold">Open YouTube board</div>
          <p className="mt-1 text-xs text-zinc-500">Search, filter scraped vs not, sync selected</p>
        </Link>
        <Link
          href="/admin-dashboard/instagram"
          className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4 transition hover:border-[#ff3b30]/40"
        >
          <Eye size={16} className="text-zinc-300" />
          <div className="mt-3 text-sm font-semibold">Instagram dashboard</div>
          <p className="mt-1 text-xs text-zinc-500">Followers, posts, scrape health, growth</p>
        </Link>
        <Link
          href="/admin-dashboard"
          className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4 transition hover:border-[#ff3b30]/40"
        >
          <Activity size={16} className="text-zinc-300" />
          <div className="mt-3 text-sm font-semibold">Overall command center</div>
          <p className="mt-1 text-xs text-zinc-500">Both platforms side by side</p>
        </Link>
      </div>
    </div>
  );
}
