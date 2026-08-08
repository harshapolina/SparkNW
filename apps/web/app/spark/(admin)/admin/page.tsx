"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AtSign, Bell, Eye, Heart, Sparkles, TrendingUp, Users } from "lucide-react";
import { api } from "@/lib/api";
import type { AdminOverviewResponse } from "@/lib/spark/api-types";
import { cn, formatNumber } from "@/lib/utils";
import { SparkAvatar } from "@/components/spark/ui";

function formatWow(pct: number): string {
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}% WoW`;
}

export default function AdminDashboardPage() {
  const { data: admin, isPending, error } = useQuery({
    queryKey: ["spark", "admin"],
    queryFn: () => api<AdminOverviewResponse>("/spark/admin"),
  });

  if (isPending && !admin) return <div className="h-64 animate-pulse rounded-2xl bg-zinc-900" />;
  if (error) {
    return (
      <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
        {(error as Error).message}
      </div>
    );
  }
  if (!admin) return null;

  const pointsWow = admin.points_wow_pct ?? 0;

  const kpis = [
    {
      label: "Total Participants",
      value: formatNumber(admin.total_participants),
      sub: "Active tracked creators",
      subClass: "text-zinc-500",
      icon: Users,
      color: "text-[#ff3b30]",
    },
    {
      label: "Total Points Distributed",
      value: formatNumber(admin.total_points_distributed),
      sub: formatWow(pointsWow),
      subClass: pointsWow >= 0 ? "text-emerald-400" : "text-rose-400",
      icon: Sparkles,
      color: "text-[#ff4d00]",
    },
    {
      label: "Instagram Accounts",
      value: formatNumber(admin.total_participants),
      sub: `${admin.ig_connected_pct}% connected`,
      subClass: "text-zinc-500",
      icon: AtSign,
      color: "text-pink-400",
    },
    {
      label: "Total Followers",
      value: formatNumber(admin.total_followers),
      sub: `New ~${formatNumber(admin.new_followers)}`,
      subClass: "text-zinc-500",
      icon: TrendingUp,
      color: "text-emerald-400",
    },
    {
      label: "Total Views",
      value: formatNumber(admin.total_views),
      sub: "Sum of scraped post views",
      subClass: "text-zinc-500",
      icon: Eye,
      color: "text-violet-400",
    },
    {
      label: "Total Likes",
      value: formatNumber(admin.total_likes),
      sub: `${formatNumber(admin.total_comments)} comments`,
      subClass: "text-zinc-500",
      icon: Heart,
      color: "text-[#ff3b30]",
    },
  ];

  const gritTotal = Math.max(1, admin.grit.qualified + admin.grit.striking + admin.grit.at_risk);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Welcome back, Admin</h1>
          <p className="mt-1 text-sm text-zinc-500">Live SPARK overview from InstaScope scrapes.</p>
        </div>
        <div className="flex flex-nowrap items-center gap-2">
          <div className="flex h-9 shrink-0 items-center rounded-xl border border-white/10 bg-[#121212] px-3 text-xs text-zinc-300 whitespace-nowrap">
            {admin.date_range}
          </div>
          <Link
            href="/notifications"
            className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/10 bg-[#121212]"
          >
            <Bell size={16} className="text-zinc-400" />
          </Link>
          <SparkAvatar initials="AD" accent size="md" />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        {kpis.map((k) => {
          const Icon = k.icon;
          return (
            <div key={k.label} className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
              <div className="flex items-start justify-between">
                <div className="text-[11px] uppercase tracking-[0.1em] text-zinc-500">{k.label}</div>
                <Icon size={16} className={k.color} />
              </div>
              <div className="mt-3 text-2xl font-semibold tabular">{k.value}</div>
              <div className={cn("mt-1 text-[11px]", k.subClass)}>{k.sub}</div>
            </div>
          );
        })}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="text-sm font-semibold">GRIT Qualification Pipeline</div>
          <p className="mt-1 text-xs text-zinc-500">Based on followers + SPARK points thresholds.</p>
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
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${(g.count / gritTotal) * 100}%`, background: g.color }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="text-sm font-semibold">Submission / Review Queue</div>
          <p className="mt-1 text-xs text-zinc-500">Scrape jobs pipeline (pending / success / failed).</p>
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
          <p className="mt-2 text-xs text-zinc-400">Low points, no weekly posts, or scrape issues.</p>
          <Link href="/spark/admin/leaderboard" className="mt-4 inline-flex text-xs font-medium text-[#ff3b30] hover:underline">
            Open admin board →
          </Link>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Growth overview</h2>
            <span className="rounded-full bg-zinc-900 px-3 py-1 text-[11px] text-zinc-400">Snapshots</span>
          </div>
          <div className="h-64">
            {(admin.growth_series?.length || 0) > 0 ? (
              <ResponsiveContainer width="100%" height="100%" debounce={40}>
                <AreaChart data={admin.growth_series}>
                  <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} width={48} />
                  <Tooltip
                    contentStyle={{ background: "#121212", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12 }}
                  />
                  <Legend />
                  <Area type="monotone" dataKey="followers" stroke="#ff3b30" fill="#ff3b3022" strokeWidth={2} isAnimationActive={false} />
                  <Area type="monotone" dataKey="views" stroke="#ff4d00" fill="#ff4d0015" strokeWidth={2} isAnimationActive={false} />
                  <Area type="monotone" dataKey="likes" stroke="#22c55e" fill="#22c55e15" strokeWidth={2} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-zinc-500">
                No snapshots yet — refresh profiles to build history.
              </div>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <h2 className="mb-4 text-sm font-semibold">Overview (Instagram)</h2>
          <div className="grid grid-cols-2 gap-3">
            {[
              ["Total Followers", formatNumber(admin.total_followers)],
              ["Total Views", formatNumber(admin.total_views)],
              ["Total Likes", formatNumber(admin.total_likes)],
              ["Total Comments", formatNumber(admin.total_comments)],
              ["Reels Posted", formatNumber(admin.reels_posted)],
              [
                "Total Points Distributed",
                `${formatNumber(admin.total_points_distributed)} (${formatWow(pointsWow)})`,
              ],
            ].map(([l, v]) => (
              <div key={l} className="rounded-xl bg-black/40 p-3">
                <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">{l}</div>
                <div className="mt-1 text-lg font-semibold tabular">{v}</div>
              </div>
            ))}
          </div>
        </div>
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
            {!admin.insights?.length && <li className="text-sm text-zinc-500">Add scraped profiles to see insights.</li>}
          </ul>
          <Link href="/analytics" className="mt-3 inline-flex text-xs font-medium text-[#ff3b30] hover:underline">
            InstaScope analytics →
          </Link>
        </div>

        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <h2 className="text-sm font-semibold">Participants Needing Attention</h2>
          <ul className="mt-4 space-y-3">
            {admin.needing_attention.map((n) => (
              <li key={n.label} className="flex items-center justify-between gap-3">
                <span className="text-sm text-zinc-300">{n.label}</span>
                <span className="font-semibold tabular">{n.count}</span>
              </li>
            ))}
          </ul>
          <Link href="/profiles" className="mt-4 inline-flex text-xs font-medium text-[#ff3b30] hover:underline">
            Open profiles →
          </Link>
        </div>

        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <h2 className="text-sm font-semibold">Scraping Health (Instagram)</h2>
          <div className="mt-5 flex flex-col items-center">
            <div className="relative flex h-28 w-28 items-center justify-center rounded-full border-[6px] border-[#22c55e]/80">
              <div className="text-center">
                <div className="text-xl font-semibold tabular">{admin.scrape.tracked}</div>
                <div className="text-[10px] text-zinc-500">tracked</div>
              </div>
            </div>
          </div>
          <dl className="mt-4 space-y-2 text-xs">
            <div className="flex justify-between">
              <dt className="text-zinc-500">Updated Today</dt>
              <dd className="tabular">{admin.scrape.updated_today}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-500">Failed</dt>
              <dd className="tabular text-rose-400">{admin.scrape.failed}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-500">Last Sync</dt>
              <dd>{admin.scrape.last_sync ? new Date(admin.scrape.last_sync).toLocaleString() : "—"}</dd>
            </div>
          </dl>
          <div className="mt-4 rounded-lg bg-emerald-500/10 px-3 py-2 text-center text-xs text-emerald-400">
            ● Live scrape pipeline connected
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-4 text-xs text-zinc-500">
        <Link href="/spark/admin/leaderboard" className="text-[#ff3b30] hover:underline">
          Admin leaderboard →
        </Link>
        <Link href="/spark/leaderboard" className="hover:text-zinc-300">
          Student leaderboard →
        </Link>
        <Link href="/profiles" className="hover:text-zinc-300">
          Profiles →
        </Link>
      </div>
    </div>
  );
}
