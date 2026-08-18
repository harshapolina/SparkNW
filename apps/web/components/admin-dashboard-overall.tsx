"use client";

import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  Camera,
  Sparkles,
  TrendingUp,
  Users,
  Video,
} from "lucide-react";
import type { AdminOverviewResponse } from "@/lib/spark/api-types";
import { cn, formatNumber, formatPct } from "@/lib/utils";
import { SparkAvatar } from "@/components/spark/ui";
import { ProgrammeWindowNote } from "@/components/programme-window-note";
import { CampusUploadsTable } from "@/components/campus-uploads-table";

function formatWow(pct: number): string {
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}% WoW`;
}

function PlatformCard({
  title,
  icon: Icon,
  href,
  accent,
  stats,
  footer,
}: {
  title: string;
  icon: typeof Video;
  href: string;
  accent: string;
  stats: { label: string; value: string; tone?: string }[];
  footer: string;
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/[0.06] bg-[#121212]">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-4">
        <div className="flex items-center gap-2.5">
          <span className={cn("grid h-8 w-8 place-items-center rounded-xl", accent)}>
            <Icon size={16} />
          </span>
          <div>
            <h2 className="text-sm font-semibold">{title}</h2>
            <p className="text-[11px] text-zinc-500">{footer}</p>
          </div>
        </div>
        <Link href={href} className="text-xs font-medium text-[#ff3b30] hover:underline">
          Open →
        </Link>
      </div>
      <div className="grid grid-cols-2 gap-px bg-white/[0.04] sm:grid-cols-3">
        {stats.map((s) => (
          <div key={s.label} className="bg-[#121212] p-4">
            <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">{s.label}</div>
            <div className={cn("mt-2 text-xl font-semibold tabular tracking-tight", s.tone)}>
              {s.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function AdminOverallDashboard({
  admin,
  unread,
}: {
  admin: AdminOverviewResponse;
  unread: number;
}) {
  const overall = admin.overall;
  const yt = admin.youtube;
  const roster = overall?.total_profiles ?? admin.total_participants;
  const igScraped = overall?.scraped_successfully ?? admin.scrape.scraped_successfully ?? 0;
  const igCoverage =
    overall?.coverage_pct ??
    (roster ? Math.min(100, Math.round((igScraped / roster) * 1000) / 10) : 0);
  const ytConnected = yt?.connected ?? 0;
  const ytScraped = yt?.scraped ?? 0;
  const ytCoverage = ytConnected ? Math.round((ytScraped / ytConnected) * 1000) / 10 : 0;
  const alerts = admin.alerts || [];
  const board = admin.leaderboard_preview || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-[0.14em] text-zinc-500">{admin.week_label}</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Command center</h1>
          <ProgrammeWindowNote
            className="mt-1"
            toDate={admin.date_range?.split("→").pop()?.trim() || admin.today?.date}
          />
          <p className="mt-1 text-sm text-zinc-500">
            Cohort health across Instagram and YouTube — drill into a platform when you need depth.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/admin-dashboard/instagram"
            className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-white/10 bg-[#121212] px-3 text-xs text-zinc-300 hover:border-[#ff4d00]/40"
          >
            <Camera size={13} /> Instagram
          </Link>
          <Link
            href="/admin-dashboard/youtube"
            className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-white/10 bg-[#121212] px-3 text-xs text-zinc-300 hover:border-[#ff4d00]/40"
          >
            <Video size={13} /> YouTube
          </Link>
          <Link
            href="/admin-alerts"
            className="relative inline-flex h-9 items-center rounded-xl border border-white/10 bg-[#121212] px-3 text-xs text-zinc-300"
          >
            Alerts
            {(unread > 0 || alerts.length > 0) && (
              <span className="ml-2 rounded-full bg-[#ff3b30] px-1.5 py-0.5 text-[9px] font-bold">
                {unread || alerts.length}
              </span>
            )}
          </Link>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
          <div className="flex items-start justify-between">
            <div className="text-[11px] uppercase tracking-[0.1em] text-zinc-500">Roster</div>
            <Users size={16} className="text-zinc-400" />
          </div>
          <div className="mt-3 text-2xl font-semibold tabular">{formatNumber(roster)}</div>
          <div className="mt-1 text-[11px] text-zinc-500">Tracked creators in cohort</div>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
          <div className="flex items-start justify-between">
            <div className="text-[11px] uppercase tracking-[0.1em] text-zinc-500">SPARK points</div>
            <Sparkles size={16} className="text-[#ff3b30]" />
          </div>
          <div className="mt-3 text-2xl font-semibold tabular">
            {formatNumber(admin.total_points_distributed)}
          </div>
          <div className="mt-1 text-[11px] text-zinc-500">{formatWow(admin.points_wow_pct ?? 0)}</div>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
          <div className="flex items-start justify-between">
            <div className="text-[11px] uppercase tracking-[0.1em] text-zinc-500">IG coverage</div>
            <Camera size={16} className="text-sky-300" />
          </div>
          <div className="mt-3 text-2xl font-semibold tabular text-lime-400">{igCoverage}%</div>
          <div className="mt-1 text-[11px] text-zinc-500">
            {formatNumber(igScraped)} scraped · {formatNumber(admin.scrape.failed)} failed
          </div>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
          <div className="flex items-start justify-between">
            <div className="text-[11px] uppercase tracking-[0.1em] text-zinc-500">YT coverage</div>
            <Video size={16} className="text-[#ff3b30]" />
          </div>
          <div className="mt-3 text-2xl font-semibold tabular text-lime-400">{ytCoverage}%</div>
          <div className="mt-1 text-[11px] text-zinc-500">
            {formatNumber(ytScraped)} scraped · {formatNumber(ytConnected)} connected
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <PlatformCard
          title="Instagram"
          icon={Camera}
          href="/admin-dashboard/instagram"
          accent="bg-sky-500/15 text-sky-300"
          footer="Followers · posts · scrape health"
          stats={[
            {
              label: "Followers",
              value: formatNumber(overall?.total_followers ?? admin.total_followers),
              tone: "text-zinc-100",
            },
            {
              label: "Updated today",
              value: formatNumber(admin.today?.updated ?? admin.scrape.updated_today),
              tone: "text-sky-300",
            },
            {
              label: "Growth today",
              value: formatNumber(admin.today?.follower_growth ?? admin.new_followers),
              tone: "text-lime-400",
            },
            {
              label: "Failed",
              value: formatNumber(overall?.failed ?? admin.scrape.failed),
              tone: (overall?.failed ?? admin.scrape.failed) > 0 ? "text-rose-400" : "text-zinc-300",
            },
            {
              label: "Private",
              value: formatNumber(overall?.private ?? admin.scrape.private ?? 0),
            },
            {
              label: "In queue",
              value: formatNumber(admin.today?.in_queue ?? admin.scrape.in_queue ?? 0),
              tone: "text-amber-300",
            },
          ]}
        />
        <PlatformCard
          title="YouTube"
          icon={Video}
          href="/admin-dashboard/youtube"
          accent="bg-[#ff3b30]/15 text-[#ff3b30]"
          footer="Subscribers · views · sync health"
          stats={[
            {
              label: "Subscribers",
              value: formatNumber(yt?.total_subscribers ?? 0),
              tone: "text-zinc-100",
            },
            {
              label: "Views",
              value: formatNumber(yt?.total_views ?? 0),
            },
            {
              label: "Videos",
              value: formatNumber(yt?.total_videos ?? 0),
            },
            {
              label: "Connected",
              value: formatNumber(ytConnected),
              tone: "text-sky-300",
            },
            {
              label: "Not scraped",
              value: formatNumber(yt?.not_scraped ?? 0),
              tone: (yt?.not_scraped ?? 0) > 0 ? "text-amber-300" : "text-zinc-300",
            },
            {
              label: "Daily sync",
              value: yt?.daily_sync_enabled ? "ON" : "OFF",
              tone: yt?.daily_sync_enabled ? "text-lime-400" : "text-zinc-400",
            },
          ]}
        />
      </div>

      <CampusUploadsTable data={admin.campus_uploads} platform="overall" />

      <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">Needs attention</h2>
              <p className="mt-0.5 text-xs text-zinc-500">Live Instagram alerts + YouTube risk counts</p>
            </div>
            <Link href="/admin-alerts" className="text-xs text-[#ff3b30] hover:underline">
              All alerts →
            </Link>
          </div>
          <div className="mb-4 grid grid-cols-3 gap-2">
            <div className="rounded-xl border border-white/[0.05] bg-black/30 px-3 py-2.5">
              <div className="text-[10px] uppercase text-zinc-500">IG failed</div>
              <div className="mt-1 text-lg font-semibold tabular text-rose-400">
                {formatNumber(admin.scrape.failed)}
              </div>
            </div>
            <div className="rounded-xl border border-white/[0.05] bg-black/30 px-3 py-2.5">
              <div className="text-[10px] uppercase text-zinc-500">YT failed</div>
              <div className="mt-1 text-lg font-semibold tabular text-rose-400">
                {formatNumber(yt?.failed ?? 0)}
              </div>
            </div>
            <div className="rounded-xl border border-white/[0.05] bg-black/30 px-3 py-2.5">
              <div className="text-[10px] uppercase text-zinc-500">At risk</div>
              <div className="mt-1 text-lg font-semibold tabular text-amber-300">
                {formatNumber(admin.at_risk_count)}
              </div>
            </div>
          </div>
          {!alerts.length ? (
            <p className="text-sm text-zinc-500">No active alerts. Cohort looks healthy.</p>
          ) : (
            <ul className="thin-scroll max-h-56 space-y-2 overflow-y-auto">
              {alerts.slice(0, 8).map((a) => (
                <li
                  key={a.id}
                  className="rounded-xl border border-white/[0.05] bg-black/25 px-3 py-2.5"
                >
                  <div className="flex items-start gap-2">
                    <AlertTriangle size={13} className="mt-0.5 shrink-0 text-[#ff3b30]" />
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{a.title}</div>
                      <div className="mt-0.5 line-clamp-1 text-[11px] text-zinc-500">{a.body}</div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">Leaderboard pulse</h2>
              <p className="mt-0.5 text-xs text-zinc-500">Top SPARK creators right now</p>
            </div>
            <Link href="/admin-leaderboard" className="text-xs text-[#ff3b30] hover:underline">
              Full board →
            </Link>
          </div>
          {!board.length ? (
            <p className="text-sm text-zinc-500">Leaderboard will fill as scrapes land.</p>
          ) : (
            <ul className="space-y-2">
              {board.slice(0, 6).map((row, idx) => (
                <li key={row.profile_id || row.username}>
                  <Link
                    href={`/admin-scraping/${row.profile_id}`}
                    className="flex items-center gap-3 rounded-xl border border-white/[0.04] bg-black/25 px-3 py-2.5 hover:border-white/10"
                  >
                    <span className="w-5 text-center text-[11px] tabular text-zinc-600">{idx + 1}</span>
                    <SparkAvatar
                      initials={(row.name || row.username || "?")
                        .slice(0, 2)
                        .toUpperCase()}
                      size="sm"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">
                        {row.name || row.username}
                      </div>
                      <div className="truncate text-[11px] text-zinc-500">@{row.username}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-semibold tabular text-[#ff3b30]">
                        {formatNumber(row.points ?? 0)}
                      </div>
                      <div
                        className={cn(
                          "text-[10px] tabular",
                          (row.growth_pct_today ?? 0) >= 0 ? "text-lime-400" : "text-rose-400"
                        )}
                      >
                        {formatPct(row.growth_pct_today ?? 0)}
                      </div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
          <TrendingUp size={15} className="text-lime-400" />
          <div className="mt-3 text-[11px] uppercase tracking-[0.1em] text-zinc-500">GRIT qualified</div>
          <div className="mt-1 text-xl font-semibold tabular">{formatNumber(admin.grit.qualified)}</div>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
          <Activity size={15} className="text-amber-300" />
          <div className="mt-3 text-[11px] uppercase tracking-[0.1em] text-zinc-500">Striking</div>
          <div className="mt-1 text-xl font-semibold tabular">{formatNumber(admin.grit.striking)}</div>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
          <AlertTriangle size={15} className="text-rose-400" />
          <div className="mt-3 text-[11px] uppercase tracking-[0.1em] text-zinc-500">At risk</div>
          <div className="mt-1 text-xl font-semibold tabular">{formatNumber(admin.grit.at_risk)}</div>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
          <Sparkles size={15} className="text-[#ff3b30]" />
          <div className="mt-3 text-[11px] uppercase tracking-[0.1em] text-zinc-500">Submissions pending</div>
          <div className="mt-1 text-xl font-semibold tabular">
            {formatNumber(admin.submissions.pending)}
          </div>
        </div>
      </div>
    </div>
  );
}
