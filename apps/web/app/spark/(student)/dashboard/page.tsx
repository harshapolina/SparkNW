"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowUpRight, BookOpen, FolderKanban, Gift, Medal } from "lucide-react";
import { api } from "@/lib/api";
import type { StudentDashboardResponse } from "@/lib/spark/api-types";
import { formatNumber } from "@/lib/utils";
import { TierBadge } from "@/components/spark/tier-badge";
import { ProgressBar, SparkAvatar } from "@/components/spark/ui";

export default function StudentDashboardPage() {
  const { data, isPending, error } = useQuery({
    queryKey: ["spark", "student"],
    queryFn: () => api<StudentDashboardResponse>("/spark/student"),
  });

  if (isPending && !data) {
    return <div className="h-64 animate-pulse rounded-2xl bg-zinc-900" />;
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
        {(error as Error).message}
      </div>
    );
  }

  if (!data || data.empty || !data.creator) {
    return (
      <div className="rounded-2xl border border-white/10 bg-[#121212] p-8 text-center">
        <h1 className="text-2xl font-semibold">No scraped profiles yet</h1>
        <p className="mt-2 text-sm text-zinc-400">
          Add Instagram profiles in InstaScope and hit Refresh — SPARK ranks them with the live point system.
        </p>
        <Link href="/profiles" className="mt-5 inline-flex text-[#ff4d00] hover:underline">
          Go to Profiles →
        </Link>
      </div>
    );
  }

  const creator = data.creator;
  const rankMove = creator.rank_delta;
  const topFive = data.top_creators || [];
  const taskHistory = data.task_history || creator.task_history || [];

  const kpis = [
    {
      label: "Current Rank",
      value: `#${creator.rank}`,
      sub: (
        <span className="text-lime-400">
          {rankMove > 0 ? `↑ +${rankMove} ranks` : rankMove < 0 ? `↓ ${Math.abs(rankMove)} ranks` : "Holds rank"}
        </span>
      ),
    },
    {
      label: "Tier",
      value: creator.tier.charAt(0) + creator.tier.slice(1).toLowerCase(),
      sub: creator.next_tier ? (
        <span className="text-zinc-400">
          {creator.points_to_next_tier} pts to {creator.next_tier}
        </span>
      ) : (
        <span className="text-zinc-400">Top tier unlocked</span>
      ),
      bar: <ProgressBar className="mt-3" value={creator.points} max={2500} color="#ff4d00" />,
    },
    {
      label: "Total Points",
      value: formatNumber(creator.points),
      sub: <span className="text-zinc-400">SPARK point system</span>,
    },
    {
      label: "Followers",
      value: formatNumber(creator.followers),
      sub: (
        <span className={creator.growth_pct_today >= 0 ? "text-lime-400" : "text-rose-400"}>
          {creator.growth_pct_today >= 0 ? "+" : ""}
          {creator.growth_pct_today.toFixed(2)}% today
          {data.followers_delta ? ` · ${data.followers_delta >= 0 ? "+" : ""}${formatNumber(data.followers_delta)}` : ""}
        </span>
      ),
    },
    {
      label: "Total Views",
      value: formatNumber(creator.views),
      sub: <span className="text-zinc-400">From scraped posts</span>,
    },
    {
      label: "Avg. Engagement",
      value: `${creator.engagement}%`,
      sub: <span className="text-zinc-400">{formatNumber(creator.avg_likes)} avg likes</span>,
    },
  ];

  const shortcuts = [
    { href: "/spark/leaderboard", label: "Leaderboard", icon: Medal },
    { href: "/profiles/" + creator.id, label: "IG Profile", icon: FolderKanban },
    { href: "/spark/admin", label: "Admin", icon: Gift },
    { href: "/imports", label: "Import", icon: BookOpen },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight md:text-4xl">
            Hey {creator.name.split(" ")[0]}.{" "}
            <span className="text-[#ff4d00]">Keep the camera rolling.</span>
          </h1>
          <p className="mt-2 text-sm text-zinc-400">
            {data.scraped === false
              ? "Waiting for the first Instagram scrape — stats show 0 until then · "
              : "Live SPARK score from scraped Instagram data · "}
            <Link href={`/profiles/${creator.id}`} className="text-[#ff4d00] hover:underline">
              {creator.handle}
            </Link>
          </p>
        </div>
        <div className="text-right text-[11px] uppercase tracking-[0.12em] text-zinc-500">
          <div>{data.week_label}</div>
          <div className="mt-0.5 normal-case tracking-normal">{data.refresh_note}</div>
        </div>
      </div>

      {data.scraped === false && (
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          Your account is live. Metrics stay at 0 until Instagram is scraped.
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        {kpis.map((k) => (
          <div key={k.label} className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
            <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-500">{k.label}</div>
            <div className="mt-2 text-2xl font-semibold tracking-tight tabular">{k.value}</div>
            <div className="mt-1 text-xs">{k.sub}</div>
            {"bar" in k ? k.bar : null}
          </div>
        ))}
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-500">Streak / Consistency</div>
          <div className="mt-3 flex items-end gap-3">
            <div className="text-4xl font-semibold tabular text-[#ff4d00]">{creator.consistency_score}</div>
            <div className="pb-1 text-sm text-zinc-400">/ 100 score</div>
          </div>
          <ProgressBar className="mt-4" value={creator.consistency_score} color="#ff4d00" />
          <p className="mt-3 text-xs text-zinc-500">
            {creator.posts_7d} posts / 7d · streak {creator.streak_weeks}
          </p>
          {creator.points_breakdown && (
            <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-zinc-400">
              <div>Consis. {creator.points_breakdown.consistency}</div>
              <div>Perf. {creator.points_breakdown.performance}</div>
              <div>Growth {creator.points_breakdown.growth}</div>
            </div>
          )}
        </div>
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5 md:col-span-2">
          <div className="mb-3 text-[11px] uppercase tracking-[0.12em] text-zinc-500">Quick navigation</div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {shortcuts.map((s) => {
              const Icon = s.icon;
              return (
                <Link
                  key={s.href}
                  href={s.href}
                  className="group flex flex-col gap-3 rounded-xl border border-white/[0.06] bg-black/40 p-4 transition hover:border-[#ff4d00]/40"
                >
                  <Icon size={18} className="text-[#ff4d00]" />
                  <span className="flex items-center justify-between text-sm font-medium">
                    {s.label}
                    <ArrowUpRight size={14} className="text-zinc-600 group-hover:text-[#ff4d00]" />
                  </span>
                </Link>
              );
            })}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.65fr_1fr]">
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Performance overview</h2>
            <span className="rounded-full bg-zinc-900 px-3 py-1 text-[11px] text-zinc-400">Snapshots</span>
          </div>
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Avg. Views", formatNumber(creator.avg_views)],
              ["Avg. Likes", formatNumber(creator.avg_likes)],
              ["Avg. Comments", formatNumber(creator.avg_comments)],
              ["Posts / 7d", String(creator.posts_7d)],
            ].map(([l, v]) => (
              <div key={l}>
                <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">{l}</div>
                <div className="mt-1 text-sm font-semibold tabular">{v}</div>
              </div>
            ))}
          </div>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%" debounce={40}>
              <AreaChart data={data.performance || []}>
                <defs>
                  <linearGradient id="sparkViewsLive" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#ff4d00" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#ff4d00" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} width={40} />
                <Tooltip
                  contentStyle={{ background: "#121212", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12 }}
                />
                <Area
                  type="monotone"
                  dataKey="followers"
                  stroke="#ff4d00"
                  fill="url(#sparkViewsLive)"
                  strokeWidth={2.5}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Leaderboard</h2>
            <Link href="/spark/leaderboard" className="text-[11px] text-[#ff4d00] hover:underline">
              Full board →
            </Link>
          </div>
          <div className="space-y-3">
            {topFive.map((row) => (
              <Link key={row.id} href={`/profiles/${row.id}`} className="flex items-center gap-3 hover:opacity-90">
                <span className="w-5 text-xs tabular text-zinc-500">{String(row.rank).padStart(2, "0")}</span>
                <SparkAvatar initials={row.initials} size="sm" accent={row.rank === 1} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{row.name}</div>
                  <div className="text-[11px] text-zinc-500">
                    {formatNumber(row.points)} pts · {formatNumber(row.followers)} followers
                  </div>
                  <ProgressBar className="mt-1.5" value={row.points} max={Math.max(creator.points, topFive[0]?.points || 1)} color="#ff3b30" />
                </div>
              </Link>
            ))}
            <div className="rounded-xl border border-[#ff4d00]/40 bg-[#ff4d00]/5 p-3">
              <div className="flex items-center gap-3">
                <span className="w-5 text-xs font-bold tabular text-[#ff4d00]">#{creator.rank}</span>
                <SparkAvatar initials={creator.initials} accent size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    {creator.name} <span className="text-[10px] font-bold text-[#ff4d00]">YOU</span>
                  </div>
                  <ProgressBar className="mt-1.5" value={creator.points} max={Math.max(creator.points, topFive[0]?.points || 1)} color="#ff4d00" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold">Task history timeline</h2>
            <p className="mt-1 text-xs text-zinc-500">Points derived from live posts + growth milestones.</p>
          </div>
          <TierBadge tier={creator.tier} />
        </div>
        {!taskHistory.length && <p className="text-sm text-zinc-500">Refresh the profile to earn performance points from posts.</p>}
        <div className="space-y-0">
          {taskHistory.map((t, i) => (
            <div key={t.id} className="relative flex gap-4 pb-5 last:pb-0">
              <div className="flex flex-col items-center">
                <div
                  className={`mt-1 h-2.5 w-2.5 rounded-full ${
                    t.status === "approved" ? "bg-lime-400" : t.status === "missed" ? "bg-rose-500" : "bg-zinc-600"
                  }`}
                />
                {i < taskHistory.length - 1 && <div className="w-px flex-1 bg-white/10" />}
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-sm font-medium">{t.title}</div>
                  <div className="text-[11px] text-zinc-500">
                    {t.category} · {t.date}
                    {t.shortcode ? (
                      <>
                        {" · "}
                        <a
                          href={`https://www.instagram.com/p/${t.shortcode}/`}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[#ff4d00] hover:underline"
                        >
                          open
                        </a>
                      </>
                    ) : null}
                  </div>
                </div>
                <div className="text-sm font-semibold tabular text-[#ff4d00]">
                  {t.points > 0 ? `+${t.points} pts` : "0 pts"}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-3 text-xs text-zinc-500">
        <span>{data.total_participants} creators ranked</span>
        <Link href="/spark/admin/leaderboard" className="text-[#ff4d00] hover:underline">
          Admin leaderboard →
        </Link>
        <Link href="/profiles" className="hover:text-zinc-300">
          Manage profiles →
        </Link>
      </div>
    </div>
  );
}
