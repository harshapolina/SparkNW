"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity,
  AlertTriangle,
  AtSign,
  BadgeCheck,
  Bell,
  Eye,
  Heart,
  Lock,
  MessageCircle,
  Sparkles,
  TrendingUp,
  Users,
  Film,
  Clock,
  Camera,
  Video,
} from "lucide-react";
import { api } from "@/lib/api";
import type { AdminOverviewResponse, AdminRecentProfile } from "@/lib/spark/api-types";
import { cn, formatNumber, formatPct } from "@/lib/utils";
import { SparkAvatar } from "@/components/spark/ui";
import { ProgrammeWindowNote } from "@/components/programme-window-note";
import { AdminYouTubeDashboard } from "@/components/admin-dashboard-youtube";
import { AdminOverallDashboard } from "@/components/admin-dashboard-overall";
import { CampusUploadsTable } from "@/components/campus-uploads-table";

export type DashboardBoardView = "overall" | "instagram" | "youtube";

type Notification = {
  id: string;
  type: string;
  title: string;
  body: string;
  is_read: boolean;
  created_at: string;
  profile_id?: string | null;
};

type KpiCard = {
  label: string;
  value: string;
  sub: string;
  icon: typeof Users;
  color: string;
};

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function formatWow(pct: number): string {
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}% WoW`;
}

function KpiGrid({ items }: { items: KpiCard[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((k) => {
        const Icon = k.icon;
        return (
          <div key={k.label} className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
            <div className="flex items-start justify-between">
              <div className="text-[11px] uppercase tracking-[0.1em] text-zinc-500">{k.label}</div>
              <Icon size={16} className={k.color} />
            </div>
            <div className="mt-3 text-2xl font-semibold tabular">{k.value}</div>
            <div className="mt-1 text-[11px] text-zinc-500">{k.sub}</div>
          </div>
        );
      })}
    </div>
  );
}

export function AdminDashboardBoard({ view }: { view: DashboardBoardView }) {
  const { data: admin, isPending, error } = useQuery({
    queryKey: ["spark", "admin"],
    queryFn: () => api<AdminOverviewResponse>("/spark/admin"),
    staleTime: 60_000,
  });
  const notifQ = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<Notification[]>("/notifications"),
  });

  const recent = admin?.recent_updates || [];
  const portfolio = admin?.portfolio || recent;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected: AdminRecentProfile | null = useMemo(() => {
    if (!recent.length) return null;
    return recent.find((p) => p.id === selectedId) || recent[0];
  }, [recent, selectedId]);

  const topProfiles = useMemo(
    () =>
      [...recent]
        .sort((a, b) => Math.abs(b.growth_pct_today) - Math.abs(a.growth_pct_today))
        .slice(0, 4),
    [recent]
  );

  const heatmapMax = useMemo(() => {
    const cells = admin?.posting_heatmap || [];
    return Math.max(1, ...cells.map((c) => c.count));
  }, [admin?.posting_heatmap]);

  if (isPending && !admin) {
    const pendingPlatform = view === "youtube" ? "youtube" : view === "overall" ? "overall" : "instagram";
    return (
      <div className="space-y-6">
        <CampusUploadsTable platform={pendingPlatform} />
        <div className="h-64 animate-pulse rounded-2xl bg-zinc-900" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
        {(error as Error).message}
      </div>
    );
  }
  if (!admin) return null;

  const unread = (notifQ.data || []).filter((n) => !n.is_read).length;

  if (view === "youtube") {
    return <AdminYouTubeDashboard admin={admin} />;
  }
  if (view === "overall") {
    return <AdminOverallDashboard admin={admin} unread={unread} />;
  }

  const pointsWow = admin.points_wow_pct ?? 0;
  const liveAlerts = admin.alerts || [];
  const contentTotal = (admin.content_types || []).reduce((a, b) => a + b.value, 0) || 1;
  const contentBars = (admin.content_types || []).slice(0, 4).map((c, i) => ({
    ...c,
    pct: Math.round((c.value / contentTotal) * 100),
    color: ["bg-[#ff3b30]", "bg-[#ff4d00]", "bg-emerald-500", "bg-violet-500"][i] || "bg-zinc-500",
  }));

  const overall = admin.overall;
  const todayBlock = admin.today;
  const totalProfiles = overall?.total_profiles ?? admin.total_participants;
  const scrapedEver =
    overall?.scraped_successfully ?? admin.scrape.scraped_successfully ?? admin.scrape.updated_today;
  const coveragePct =
    overall?.coverage_pct ??
    (totalProfiles ? Math.min(100, Math.round((scrapedEver / totalProfiles) * 1000) / 10) : 0);
  const freshnessPct = totalProfiles
    ? Math.min(
        100,
        Math.round(
          (((todayBlock?.updated ?? admin.scrape.updated_today) / totalProfiles) * 100)
        )
      )
    : 0;

  const overallKpis: KpiCard[] = [
    {
      label: "Total Profiles",
      value: formatNumber(totalProfiles),
      sub: "Unique roster accounts",
      icon: Users,
      color: "text-[#ff3b30]",
    },
    {
      label: "Scraped Successfully",
      value: formatNumber(scrapedEver),
      sub: `${formatNumber(overall?.scraped_public ?? scrapedEver - (overall?.scraped_private ?? overall?.private_scraped ?? 0))} public + ${formatNumber(overall?.scraped_private ?? overall?.private_scraped ?? 0)} private · ${coveragePct}% · no duplicates`,
      icon: BadgeCheck,
      color: "text-emerald-400",
    },
    {
      label: "Failed",
      value: formatNumber(overall?.failed ?? admin.failed_updates ?? admin.scrape.failed),
      sub: "Exclusive status bucket",
      icon: AlertTriangle,
      color: "text-rose-400",
    },
    {
      label: "Unavailable",
      value: formatNumber(overall?.unavailable ?? admin.scrape.unavailable ?? 0),
      sub: "IG username missing",
      icon: AlertTriangle,
      color: "text-amber-400",
    },
    {
      label: "Private (subset)",
      value: formatNumber(overall?.private_scraped ?? overall?.scraped_private ?? admin.scrape.private ?? 0),
      sub: "Already inside Scraped Successfully — do not add again",
      icon: Lock,
      color: "text-violet-400",
    },
    {
      label: "Paused",
      value: formatNumber(overall?.paused ?? 0),
      sub: "Manually paused",
      icon: Clock,
      color: "text-zinc-400",
    },
    {
      label: "Not Scraped Yet",
      value: formatNumber(overall?.pending ?? admin.scrape.pending ?? 0),
      sub: "No IG card data yet",
      icon: Clock,
      color: "text-zinc-400",
    },
    {
      label: "Avg Engagement",
      value: `${overall?.average_engagement ?? admin.average_engagement}%`,
      sub: "Portfolio avg",
      icon: TrendingUp,
      color: "text-emerald-400",
    },
    {
      label: "Avg Followers",
      value: formatNumber(overall?.average_followers ?? admin.average_followers ?? 0),
      sub: "Across tracked profiles",
      icon: Users,
      color: "text-pink-400",
    },
    {
      label: "Avg Likes",
      value: formatNumber(overall?.average_likes ?? admin.average_likes ?? 0),
      sub: `Views ${formatNumber(overall?.average_views ?? admin.average_views ?? 0)}`,
      icon: Heart,
      color: "text-[#ff3b30]",
    },
    {
      label: "Avg Views",
      value: formatNumber(overall?.average_views ?? admin.average_views ?? 0),
      sub: "From scraped posts",
      icon: Eye,
      color: "text-violet-400",
    },
    {
      label: "Total Points",
      value: formatNumber(overall?.total_points ?? admin.total_points_distributed),
      sub: formatWow(pointsWow),
      icon: Sparkles,
      color: "text-[#ff4d00]",
    },
    {
      label: "Total Followers",
      value: formatNumber(overall?.total_followers ?? admin.total_followers),
      sub: `${admin.ig_connected_pct}% IG connected`,
      icon: AtSign,
      color: "text-emerald-400",
    },
    {
      label: "Total Views",
      value: formatNumber(overall?.total_views ?? admin.total_views),
      sub: "Sum of scraped post views",
      icon: Eye,
      color: "text-violet-400",
    },
    {
      label: "Total Engagement",
      value: formatNumber(overall?.total_engagement ?? admin.total_engagement),
      sub: `${formatNumber(overall?.total_likes ?? admin.total_likes)} likes · ${formatNumber(overall?.total_comments ?? admin.total_comments)} comments`,
      icon: Heart,
      color: "text-[#ff3b30]",
    },
    {
      label: "Total Likes",
      value: formatNumber(overall?.total_likes ?? admin.total_likes),
      sub: "Across scraped posts (unique profiles)",
      icon: Heart,
      color: "text-rose-300",
    },
    {
      label: "Total Comments",
      value: formatNumber(overall?.total_comments ?? admin.total_comments),
      sub: "Across scraped posts",
      icon: MessageCircle,
      color: "text-sky-300",
    },
    {
      label: "Reels Posted",
      value: formatNumber(overall?.reels_posted ?? admin.reels_posted),
      sub: "In scraped set",
      icon: Film,
      color: "text-amber-400",
    },
    {
      label: "At-Risk Creators",
      value: formatNumber(overall?.at_risk_count ?? admin.at_risk_count),
      sub: "GRIT / inactive flags",
      icon: AlertTriangle,
      color: "text-[#ff3b30]",
    },
  ];

  const todayKpis: KpiCard[] = [
    {
      label: "Updated Today",
      value: formatNumber(todayBlock?.updated ?? admin.profiles_updated_today ?? admin.scrape.updated_today),
      sub: `Fresh successful scrapes · ${todayBlock?.date ?? "today"}`,
      icon: Activity,
      color: "text-sky-400",
    },
    {
      label: "Failed Today",
      value: formatNumber(todayBlock?.failed ?? 0),
      sub: (todayBlock?.failed ?? 0) ? "Review alerts" : "No failures today",
      icon: AlertTriangle,
      color: "text-rose-400",
    },
    {
      label: "Private Updated Today",
      value: formatNumber(todayBlock?.private_updated ?? 0),
      sub: "Private accounts scraped today",
      icon: Lock,
      color: "text-violet-400",
    },
    {
      label: "Follower Growth Today",
      value: formatNumber(todayBlock?.follower_growth ?? admin.follower_growth_today ?? admin.new_followers),
      sub: "Estimated from scrapes",
      icon: TrendingUp,
      color: "text-lime-400",
    },
    {
      label: "In Queue Now",
      value: formatNumber(todayBlock?.in_queue ?? admin.scrape.in_queue ?? 0),
      sub: "Live scrape progress active",
      icon: Clock,
      color: "text-amber-300",
    },
    {
      label: "Today Coverage",
      value: `${freshnessPct}%`,
      sub: `${formatNumber(todayBlock?.updated ?? admin.scrape.updated_today)} of ${formatNumber(totalProfiles)} refreshed today`,
      icon: BadgeCheck,
      color: "text-emerald-400",
    },
  ];

  const gritTotal = Math.max(1, admin.grit.qualified + admin.grit.striking + admin.grit.at_risk);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-[0.14em] text-zinc-500">{admin.week_label}</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Instagram intelligence</h1>
          <ProgrammeWindowNote className="mt-1" toDate={admin.date_range?.split("→").pop()?.trim() || admin.today?.date} />
          <p className="mt-1 text-sm text-zinc-500">
            Followers, posts, scrape health, and growth — Instagram only.
          </p>
        </div>
        <div className="flex flex-nowrap items-center gap-2 overflow-x-auto pb-0.5">
          <div className="flex h-9 shrink-0 items-center rounded-xl border border-white/10 bg-[#121212] px-3 text-xs text-zinc-300 whitespace-nowrap">
            {admin.date_range}
          </div>
          <Link
            href="/admin-dashboard/youtube"
            className="flex h-9 shrink-0 items-center gap-1.5 rounded-xl border border-white/10 bg-[#121212] px-3 text-xs text-zinc-300 whitespace-nowrap hover:border-[#ff4d00]/40"
          >
            <Video size={13} /> YouTube dash
          </Link>
          <Link
            href="/admin-scraping/instagram"
            className="flex h-9 shrink-0 items-center gap-1.5 rounded-xl border border-white/10 bg-[#121212] px-3 text-xs text-zinc-300 whitespace-nowrap hover:border-[#ff4d00]/40"
          >
            <Camera size={13} /> IG board
          </Link>
          <Link
            href="/admin-settings"
            className="flex h-9 shrink-0 items-center rounded-xl border border-white/10 bg-[#121212] px-3 text-xs text-zinc-300 whitespace-nowrap hover:border-[#ff4d00]/40"
          >
            Settings
          </Link>
          <Link
            href="/admin-alerts"
            className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/10 bg-[#121212]"
          >
            <Bell size={16} className="text-zinc-400" />
            {(unread > 0 || liveAlerts.length > 0) && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#ff3b30] px-1 text-[9px] font-bold">
                {unread || liveAlerts.length}
              </span>
            )}
          </Link>
          <SparkAvatar initials="AD" accent size="md" />
        </div>
      </div>

      <div className="flex gap-3 overflow-x-auto pb-1">
        {topProfiles.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => setSelectedId(p.id)}
            className={cn(
              "flex min-w-[200px] items-center gap-3 rounded-2xl border bg-[#121212] px-3 py-2.5 text-left transition",
              selected?.id === p.id ? "border-[#ff3b30]/50" : "border-white/[0.06] hover:border-white/20"
            )}
          >
            <SparkAvatar initials={p.username.slice(0, 2).toUpperCase()} size="sm" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1 truncate text-sm font-semibold">
                @{p.username}
                {p.is_verified && <BadgeCheck size={12} className="text-sky-400" />}
              </div>
              <div className="truncate text-[11px] text-zinc-500">{p.full_name || p.campus || "Tracked"}</div>
            </div>
            <span
              className={cn(
                "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold tabular",
                p.growth_pct_today >= 0 ? "bg-emerald-500/15 text-emerald-400" : "bg-rose-500/15 text-rose-400"
              )}
            >
              {formatPct(p.growth_pct_today)}
            </span>
          </button>
        ))}
        {!topProfiles.length && (
          <Link href="/admin-scraping" className="rounded-2xl border border-dashed border-white/10 px-4 py-3 text-sm text-zinc-500">
            Add creators to see top movers →
          </Link>
        )}
      </div>

      <section className="space-y-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#ff3b30]">
            Overall data
          </div>
          <ProgrammeWindowNote
            className="mt-1 !text-xs"
            toDate={admin.today?.date || admin.date_range?.split("→").pop()?.trim()}
          />
          <p className="mt-1 text-sm text-zinc-500">
            Exclusive status math:{" "}
            <span className="text-zinc-300">
              Scraped + Failed + Unavailable + Paused + Not scraped = Total ({formatNumber(totalProfiles)})
            </span>
            . Private is a subset of Scraped — do not add it again. Totals (likes, views, points) use the programme window above.
          </p>
        </div>
        <KpiGrid items={overallKpis} />
      </section>

      <section className="space-y-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-sky-400">
            Today&apos;s data
          </div>
          <p className="mt-1 text-sm text-zinc-500">
            Day-based scrape activity for {todayBlock?.date ?? "today"} (UTC).
          </p>
        </div>
        <KpiGrid items={todayKpis} />
      </section>

      {/* Alerts */}
      <div className="rounded-2xl border border-rose-500/20 bg-rose-500/[0.06] p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <AlertTriangle size={16} className="text-rose-400" />
            <h2 className="text-sm font-semibold">Alerts & notifications</h2>
            <span className="rounded-full bg-rose-500/20 px-2 py-0.5 text-[10px] font-semibold text-rose-300">
              {liveAlerts.length} live · {unread} unread
            </span>
          </div>
          <Link href="/admin-alerts" className="text-xs font-medium text-[#ff3b30] hover:underline">
            Open alerts center →
          </Link>
        </div>
        <ul className="mt-4 space-y-2">
          {liveAlerts.slice(0, 5).map((a) => (
            <li key={a.id}>
              <Link
                href={`/admin-scraping/${a.profile_id}`}
                className="flex items-start justify-between gap-3 rounded-xl border border-white/[0.04] bg-black/30 px-3 py-2.5 hover:border-rose-500/30"
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium">{a.title}</div>
                  <div className="mt-0.5 truncate text-xs text-zinc-500">{a.body}</div>
                </div>
                <span className="shrink-0 rounded-full bg-rose-500/15 px-2 py-0.5 text-[10px] uppercase text-rose-300">
                  {a.type.replaceAll("_", " ")}
                </span>
              </Link>
            </li>
          ))}
          {!liveAlerts.length && <li className="text-sm text-zinc-500">All quiet — no scrape failures or big growth swings.</li>}
        </ul>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="text-sm font-semibold">GRIT Qualification Pipeline</div>
          <div className="mt-5 space-y-3">
            {[
              { label: "Qualified (50K+)", count: admin.grit.qualified, color: "#22c55e" },
              { label: "Striking distance", count: admin.grit.striking, color: "#ff4d00" },
              { label: "At risk / not eligible", count: admin.grit.at_risk, color: "#ff3b30" },
            ].map((g) => (
              <div key={g.label}>
                <div className="mb-1 flex justify-between text-xs">
                  <span className="text-zinc-400">{g.label}</span>
                  <span className="font-semibold tabular">{g.count}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
                  <div className="h-full rounded-full" style={{ width: `${(g.count / gritTotal) * 100}%`, background: g.color }} />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="text-sm font-semibold">Submission / Review Queue</div>
          <div className="mt-5 grid grid-cols-3 gap-3">
            {[
              { label: "Pending", count: admin.submissions.pending, color: "text-amber-400" },
              { label: "Approved", count: admin.submissions.approved, color: "text-lime-400" },
              { label: "Rejected", count: admin.submissions.rejected, color: "text-rose-400" },
            ].map((s) => (
              <div key={s.label} className="rounded-xl bg-black/40 p-3 text-center">
                <div className={`text-2xl font-semibold tabular ${s.color}`}>{s.count}</div>
                <div className="mt-1 text-[10px] uppercase tracking-[0.1em] text-zinc-500">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-[#ff3b30]/30 bg-[#ff3b30]/5 p-5">
          <div className="text-sm font-semibold">At-Risk / Inactive</div>
          <div className="mt-3 text-4xl font-semibold tabular text-[#ff3b30]">{admin.at_risk_count}</div>
          <Link href="/admin-scraping" className="mt-4 inline-flex text-xs font-medium text-[#ff3b30] hover:underline">
            Open scraping table →
          </Link>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
              <h2 className="text-sm font-semibold">Content performance</h2>
              <p className="mt-0.5 text-xs text-zinc-500">Mix across recent scraped posts</p>
              <div className="mt-5 space-y-4">
                {contentBars.length ? (
                  contentBars.map((bar) => (
                    <div key={bar.name}>
                      <div className="mb-1.5 flex justify-between text-sm">
                        <span className="capitalize text-zinc-300">{bar.name}</span>
                        <span className="tabular text-zinc-500">{bar.pct}%</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
                        <div className={`h-full rounded-full ${bar.color}`} style={{ width: `${bar.pct}%` }} />
                      </div>
                      <div className="mt-1.5 grid grid-cols-3 gap-2 text-[11px] text-zinc-500">
                        <div>Count <span className="font-medium text-zinc-300">{bar.value}</span></div>
                        <div>Share <span className="font-medium text-zinc-300">{bar.pct}%</span></div>
                        <div>Status <span className="font-medium text-zinc-300">Tracked</span></div>
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-zinc-500">Refresh profiles to populate content mix.</p>
                )}
              </div>
              <div className="mt-5 rounded-xl bg-black/40 px-4 py-3">
                <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">Follower growth today</div>
                <div className="mt-1 text-xl font-semibold tabular">
                  {formatNumber(admin.follower_growth_today ?? admin.new_followers)}
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
              <h2 className="text-sm font-semibold">Monitoring activity</h2>
              <p className="mt-0.5 text-xs text-zinc-500">Lifetime coverage vs today&apos;s refresh</p>
              <div className="mt-4 space-y-4">
                <div>
                  <div className="mb-1.5 flex justify-between text-xs">
                    <span className="text-zinc-500">Scraped till date</span>
                    <span className="font-medium tabular text-emerald-400">{coveragePct}%</span>
                  </div>
                  <div className="h-2.5 overflow-hidden rounded-full bg-zinc-800">
                    <div
                      className="h-full rounded-full bg-emerald-500"
                      style={{ width: `${Math.min(100, coveragePct)}%` }}
                    />
                  </div>
                  <p className="mt-1 text-[11px] text-zinc-600">
                    {formatNumber(scrapedEver)} of {formatNumber(totalProfiles)} unique accounts
                  </p>
                </div>
                <div>
                  <div className="mb-1.5 flex justify-between text-xs">
                    <span className="text-zinc-500">Freshness today</span>
                    <span className="font-medium tabular">{freshnessPct}%</span>
                  </div>
                  <div className="h-2.5 overflow-hidden rounded-full bg-zinc-800">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-[#ff3b30] via-[#ff4d00] to-emerald-500"
                      style={{ width: `${freshnessPct}%` }}
                    />
                  </div>
                  <p className="mt-1 text-[11px] text-zinc-600">
                    {formatNumber(todayBlock?.updated ?? admin.scrape.updated_today)} refreshed today
                  </p>
                </div>
              </div>
              <div className="mt-4 space-y-2">
                {recent.slice(0, 6).map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setSelectedId(p.id)}
                    className="flex w-full items-center gap-3 rounded-xl bg-black/40 px-3 py-2.5 text-left hover:bg-black/60"
                  >
                    <SparkAvatar initials={p.username.slice(0, 2).toUpperCase()} size="sm" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">@{p.username}</div>
                      <div className="text-[11px] text-zinc-500">
                        {p.last_scraped_at ? new Date(p.last_scraped_at).toLocaleString() : "Not scraped yet"}
                      </div>
                    </div>
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-[10px] capitalize",
                        p.status === "failed" || p.status === "unavailable"
                          ? "bg-rose-500/15 text-rose-400"
                          : "bg-emerald-500/15 text-emerald-400"
                      )}
                    >
                      {p.status}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          <CampusUploadsTable platform="instagram" />

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
              <h2 className="mb-3 text-sm font-semibold">Followers over time</h2>
              <p className="mb-3 text-xs text-zinc-500">Portfolio average from daily snapshots</p>
              <div className="h-52">
                {(admin.followers_over_time?.length || 0) > 0 ? (
                  <ResponsiveContainer width="100%" height="100%" debounce={40}>
                    <AreaChart data={admin.followers_over_time}>
                      <defs>
                        <linearGradient id="avgFollowers" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#ff3b30" stopOpacity={0.35} />
                          <stop offset="100%" stopColor="#ff3b30" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
                      <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false} width={40} />
                      <Tooltip contentStyle={{ background: "#121212", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12 }} />
                      <Area type="monotone" dataKey="value" stroke="#ff3b30" fill="url(#avgFollowers)" strokeWidth={2.5} isAnimationActive={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-zinc-500">No snapshot history yet.</div>
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
              <h2 className="mb-3 text-sm font-semibold">Posts per day</h2>
              <p className="mb-3 text-xs text-zinc-500">Scraped post volume across the cohort</p>
              <div className="h-52">
                {(admin.posts_per_day?.length || 0) > 0 ? (
                  <ResponsiveContainer width="100%" height="100%" debounce={40}>
                    <BarChart data={admin.posts_per_day}>
                      <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
                      <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false} width={32} />
                      <Tooltip contentStyle={{ background: "#121212", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12 }} />
                      <Bar dataKey="value" fill="#ff4d00" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-zinc-500">No posts yet.</div>
                )}
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
            <h2 className="mb-1 text-sm font-semibold">Growth overview</h2>
            <p className="mb-3 text-xs text-zinc-500">Summed followers / views / likes from snapshots</p>
            <div className="h-64">
              {(admin.growth_series?.length || 0) > 0 ? (
                <ResponsiveContainer width="100%" height="100%" debounce={40}>
                  <AreaChart data={admin.growth_series}>
                    <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
                    <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} width={48} />
                    <Tooltip contentStyle={{ background: "#121212", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12 }} />
                    <Legend />
                    <Area type="monotone" dataKey="followers" stroke="#ff3b30" fill="#ff3b3022" strokeWidth={2} isAnimationActive={false} />
                    <Area type="monotone" dataKey="views" stroke="#ff4d00" fill="#ff4d0015" strokeWidth={2} isAnimationActive={false} />
                    <Area type="monotone" dataKey="likes" stroke="#22c55e" fill="#22c55e15" strokeWidth={2} isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-zinc-500">No snapshots yet.</div>
              )}
            </div>
          </div>

          {/* Posting heatmap */}
          <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
            <h2 className="mb-1 text-sm font-semibold">Posting heatmap</h2>
            <p className="mb-4 text-xs text-zinc-500">When the cohort posts (day × hour, from scraped timestamps)</p>
            {(admin.posting_heatmap?.length || 0) > 0 ? (
              <div className="overflow-x-auto">
                <div className="inline-grid min-w-[640px] gap-0.5" style={{ gridTemplateColumns: `48px repeat(24, minmax(0, 1fr))` }}>
                  <div />
                  {Array.from({ length: 24 }, (_, h) => (
                    <div key={h} className="text-center text-[9px] text-zinc-600">
                      {h}
                    </div>
                  ))}
                  {DAY_LABELS.map((label, day) => (
                    <div key={label} className="contents">
                      <div className="flex items-center text-[10px] text-zinc-500">{label}</div>
                      {Array.from({ length: 24 }, (_, hour) => {
                        const cell = (admin.posting_heatmap || []).find((c) => c.day === day && c.hour === hour);
                        const count = cell?.count || 0;
                        const intensity = count / heatmapMax;
                        return (
                          <div
                            key={`${day}-${hour}`}
                            title={`${label} ${hour}:00 — ${count} posts`}
                            className="aspect-square rounded-[2px]"
                            style={{
                              background:
                                count === 0
                                  ? "rgba(255,255,255,0.03)"
                                  : `rgba(255, 59, 48, ${0.15 + intensity * 0.85})`,
                            }}
                          />
                        );
                      })}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-zinc-500">Refresh profiles to build posting patterns.</p>
            )}
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
              <h2 className="text-sm font-semibold">Weekly Growth Insights</h2>
              <ul className="mt-4 space-y-3">
                {(admin.insights || []).map((i) => (
                  <li key={i.label} className="flex items-start justify-between gap-3 border-b border-white/[0.04] pb-3 last:border-0">
                    <div>
                      <div className="text-[11px] text-zinc-500">{i.label}</div>
                      <div className="text-sm font-medium">{i.name}</div>
                    </div>
                    <div className="text-sm font-semibold tabular text-[#ff3b30]">{i.value}</div>
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
              <h2 className="text-sm font-semibold">Needing Attention</h2>
              <ul className="mt-4 space-y-3">
                {admin.needing_attention.map((n) => (
                  <li key={n.label} className="flex items-center justify-between gap-3">
                    <span className="text-sm text-zinc-300">{n.label}</span>
                    <span className="font-semibold tabular">{n.count}</span>
                  </li>
                ))}
              </ul>
              <Link href="/admin-scraping" className="mt-4 inline-flex text-xs font-medium text-[#ff3b30] hover:underline">
                Open scraping →
              </Link>
            </div>
            <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
              <h2 className="text-sm font-semibold">Scraping Health</h2>
              <dl className="mt-4 space-y-2 text-xs">
                <div className="flex justify-between"><dt className="text-zinc-500">Tracked</dt><dd className="tabular">{admin.scrape.tracked}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">Scraped till date</dt><dd className="tabular text-emerald-400">{admin.scrape.scraped_successfully ?? scrapedEver}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">Updated Today</dt><dd className="tabular">{admin.scrape.updated_today}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">Failed</dt><dd className="tabular text-rose-400">{admin.scrape.failed}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">Unavailable</dt><dd className="tabular text-amber-400">{admin.scrape.unavailable ?? 0}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">Private</dt><dd className="tabular">{admin.scrape.private ?? 0}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">Pending</dt><dd className="tabular">{admin.scrape.pending ?? 0}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">In queue</dt><dd className="tabular">{admin.scrape.in_queue ?? 0}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">Last Sync</dt><dd>{admin.scrape.last_sync ? new Date(admin.scrape.last_sync).toLocaleString() : "—"}</dd></div>
                <div className="flex justify-between"><dt className="text-zinc-500">Next Sync</dt><dd>{admin.scrape.next_sync}</dd></div>
              </dl>
            </div>
          </div>

          <Link
            href="/admin-dashboard/youtube"
            className="flex flex-col gap-3 rounded-2xl border border-white/[0.06] bg-[#121212] p-5 transition hover:border-[#ff3b30]/35 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="flex items-start gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#ff3b30]/15 text-[#ff3b30]">
                <Video size={18} />
              </span>
              <div>
                <h2 className="text-sm font-semibold">YouTube lives on its own dashboard</h2>
                <p className="mt-1 text-xs text-zinc-500">
                  {formatNumber(admin.youtube?.connected ?? 0)} connected ·{" "}
                  {formatNumber(admin.youtube?.scraped ?? 0)} scraped ·{" "}
                  {formatNumber(admin.youtube?.total_subscribers ?? 0)} subscribers
                </p>
              </div>
            </div>
            <span className="text-xs font-medium text-[#ff3b30]">Open YouTube intelligence →</span>
          </Link>

          {/* Portfolio analytics grid (old /analytics) */}
          <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold">Portfolio analytics</h2>
                <p className="mt-0.5 text-xs text-zinc-500">Every tracked creator — open for full fields</p>
              </div>
              <Link href="/admin-analytics" className="text-xs text-[#ff3b30] hover:underline">
                Full grid →
              </Link>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {portfolio.slice(0, 9).map((p) => (
                <Link
                  key={p.id}
                  href={`/admin-scraping/${p.id}`}
                  className="rounded-xl border border-white/[0.04] bg-black/40 p-4 transition hover:border-[#ff3b30]/40"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1 truncate font-semibold">
                        @{p.username}
                        {p.is_verified && <BadgeCheck size={12} className="text-sky-400" />}
                        {p.is_private && <span className="text-[9px] text-amber-400">PRIV</span>}
                      </div>
                      <div className="truncate text-xs text-zinc-500">{p.full_name || p.campus}</div>
                    </div>
                    <span className={cn("text-[10px] tabular", p.growth_pct_today >= 0 ? "text-emerald-400" : "text-rose-400")}>
                      {formatPct(p.growth_pct_today)}
                    </span>
                  </div>
                  <div className="mt-4 grid grid-cols-3 gap-2 border-t border-white/[0.04] pt-3 text-center">
                    <div>
                      <div className="text-[9px] uppercase text-zinc-500">Followers</div>
                      <div className="mt-0.5 text-xs font-semibold tabular">{formatNumber(p.followers)}</div>
                    </div>
                    <div>
                      <div className="text-[9px] uppercase text-zinc-500">Engage</div>
                      <div className="mt-0.5 text-xs font-semibold tabular">{p.engagement_rate.toFixed(2)}%</div>
                    </div>
                    <div>
                      <div className="text-[9px] uppercase text-zinc-500">Avg likes</div>
                      <div className="mt-0.5 text-xs font-semibold tabular">{formatNumber(p.avg_likes)}</div>
                    </div>
                  </div>
                </Link>
              ))}
              {!portfolio.length && <p className="text-sm text-zinc-500">Add profiles to analyze.</p>}
            </div>
          </div>
        </div>

        <aside className="space-y-4">
          <div className="overflow-hidden rounded-2xl border border-white/[0.06] bg-[#121212]">
            {selected ? (
              <>
                <div className="bg-gradient-to-br from-[#ff3b30]/20 via-[#121212] to-black px-6 pb-8 pt-8 text-center">
                  <div className="mx-auto w-fit">
                    <SparkAvatar initials={selected.username.slice(0, 2).toUpperCase()} accent />
                  </div>
                  <div className="mt-4 flex items-center justify-center gap-1.5">
                    <h2 className="text-lg font-semibold">@{selected.username}</h2>
                    {selected.is_verified && <BadgeCheck size={16} className="text-sky-400" />}
                  </div>
                  <p className="mt-1 text-sm text-zinc-500">{selected.full_name || "Instagram profile"}</p>
                  {selected.bio && <p className="mt-2 line-clamp-2 text-xs text-zinc-500">{selected.bio}</p>}
                </div>
                <div className="-mt-4 flex flex-wrap justify-center gap-2 px-4">
                  <Link href={`/admin-scraping/${selected.id}`} className="rounded-xl bg-[#ff3b30] px-3 py-2 text-xs font-semibold">
                    Open
                  </Link>
                  <div className="rounded-xl border border-white/10 bg-black/50 px-3 py-2 text-xs tabular text-zinc-400">
                    {formatPct(selected.growth_pct_today)} growth
                  </div>
                  <div className="rounded-xl border border-white/10 bg-black/50 px-3 py-2 text-xs capitalize text-zinc-400">
                    {selected.status}
                  </div>
                  {selected.is_private && (
                    <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
                      Private
                    </div>
                  )}
                  {selected.is_business && (
                    <div className="rounded-xl border border-white/10 bg-black/50 px-3 py-2 text-xs text-zinc-400">
                      Business
                    </div>
                  )}
                </div>
                <div className="space-y-3 px-5 py-5">
                  {[
                    ["Followers", formatNumber(selected.followers)],
                    ["Following", formatNumber(selected.following)],
                    ["Posts", formatNumber(selected.posts_count)],
                    ["Avg likes", formatNumber(selected.avg_likes)],
                    ["Avg views", formatNumber(selected.avg_views)],
                    ["Avg comments", formatNumber(selected.avg_comments ?? 0)],
                    ["Engagement", `${selected.engagement_rate.toFixed(2)}%`],
                    ["F/F ratio", (selected.follower_following_ratio ?? 0).toFixed(2)],
                    ["Highlights", formatNumber(selected.highlight_reel_count ?? 0)],
                    ["Category", selected.category || "—"],
                    ["Campus", selected.campus || "—"],
                    ["Student ID", selected.student_id || "—"],
                    ["Website", selected.website || "—"],
                    ["Verified", selected.is_verified ? "Yes" : "No"],
                    ["Private", selected.is_private ? "Yes" : "No"],
                    ["Last scraped", selected.last_scraped_at ? new Date(selected.last_scraped_at).toLocaleString() : "—"],
                  ].map(([label, value]) => (
                    <div key={label} className="flex items-center justify-between gap-3 border-b border-white/[0.04] pb-2.5 last:border-0">
                      <span className="text-sm text-zinc-500">{label}</span>
                      <span className="max-w-[55%] truncate text-right text-sm font-semibold tabular">{value}</span>
                    </div>
                  ))}
                  {selected.last_error && (
                    <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
                      {selected.last_error}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="p-8 text-center text-sm text-zinc-500">Add a creator to see details here.</div>
            )}
          </div>

          <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold">Leaderboard preview</h2>
              <Link href="/admin-leaderboard" className="text-[11px] text-[#ff3b30] hover:underline">Full board →</Link>
            </div>
            <div className="space-y-2">
              {(admin.leaderboard_preview || []).slice(0, 6).map((row) => (
                <Link key={row.id} href={`/admin-scraping/${row.id}`} className="flex items-center gap-2.5 rounded-xl px-2 py-1.5 hover:bg-white/[0.03]">
                  <span className="w-5 text-[11px] tabular text-zinc-500">{String(row.rank).padStart(2, "0")}</span>
                  <SparkAvatar initials={row.initials} size="sm" accent={row.rank === 1} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm">{row.name}</div>
                    <div className="text-[10px] text-zinc-500">{formatNumber(row.points)} pts</div>
                  </div>
                </Link>
              ))}
            </div>
          </div>

          <Link href="/admin-import" className="block rounded-2xl border border-white/10 bg-gradient-to-br from-[#1a1a1a] to-black px-5 py-4 hover:border-[#ff3b30]/40">
            <div className="text-sm font-semibold">Import from sheets</div>
            <div className="mt-1 text-xs text-zinc-500">CSV, Excel, or Google Sheets → roster + scrape</div>
          </Link>
          <Link href="/admin-duplicates" className="block rounded-2xl border border-white/[0.06] bg-[#121212] px-5 py-4 hover:border-white/20">
            <div className="text-sm font-semibold">Import duplicates</div>
            <div className="mt-1 text-xs text-zinc-500">Review accounts already tracked on re-import</div>
          </Link>
          <Link href="/admin-unimported" className="block rounded-2xl border border-white/[0.06] bg-[#121212] px-5 py-4 hover:border-white/20">
            <div className="text-sm font-semibold">Unimported rows</div>
            <div className="mt-1 text-xs text-zinc-500">Missing IG, invalid handles, sheet dupes</div>
          </Link>
        </aside>
      </div>

      <div className="flex flex-wrap gap-4 text-xs text-zinc-500">
        <Link href="/admin-scraping" className="text-[#ff3b30] hover:underline">Scraping →</Link>
        <Link href="/admin-alerts" className="text-[#ff3b30] hover:underline">Alerts →</Link>
        <Link href="/admin-analytics" className="text-[#ff3b30] hover:underline">Analytics →</Link>
        <Link href="/admin-settings" className="text-[#ff3b30] hover:underline">Settings →</Link>
        <Link href="/admin-import" className="hover:text-zinc-300">Import →</Link>
        <Link href="/admin-duplicates" className="hover:text-zinc-300">Duplicates →</Link>
        <Link href="/admin-unimported" className="hover:text-zinc-300">Unimported →</Link>
        <Link href="/admin-leaderboard" className="hover:text-zinc-300">Leaderboard →</Link>
        <Link href="/top-10" className="hover:text-zinc-300">Top 10 →</Link>
      </div>
    </div>
  );
}
