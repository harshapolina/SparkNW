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
import { ProgrammeWindowNote } from "@/components/programme-window-note";

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
          Your profile is not on the board yet. Ask an admin to import and scrape your Instagram handle.
        </p>
        <Link href="/top-10" className="mt-5 inline-flex text-[#ff4d00] hover:underline">
          View public Top 10 →
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
      label: "Consistency",
      value: String(creator.consistency_score),
      sub: <span className="text-zinc-400">/ 100 · streak {creator.streak_weeks}</span>,
      bar: <ProgressBar className="mt-3" value={creator.consistency_score} color="#ff4d00" />,
    },
    {
      label: "Avg. Engagement",
      value: `${creator.engagement}%`,
      sub: (
        <span className="text-zinc-400">
          {formatNumber(creator.avg_views)} views · {formatNumber(creator.avg_likes)} likes ·{" "}
          {formatNumber(creator.avg_comments)} comments
        </span>
      ),
    },
  ];

  const shortcuts = [
    { href: "/student-leaderboard", label: "Leaderboard", icon: Medal },
    { href: "/top-10", label: "Top 10", icon: Gift },
    { href: "/spark/projects", label: "Projects", icon: FolderKanban },
    { href: "/spark/resources", label: "Resources", icon: BookOpen },
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
            Live SPARK score from scraped Instagram data ·{" "}
            <span className="text-[#ff4d00]">{creator.handle}</span>
          </p>
          <ProgrammeWindowNote className="mt-2 !text-xs" />
        </div>
        <div className="text-right text-[11px] uppercase tracking-[0.12em] text-zinc-500">
          <div>{data.week_label}</div>
          <div className="mt-0.5 normal-case tracking-normal">{data.refresh_note}</div>
        </div>
      </div>

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

      <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold">Your YouTube</h2>
            <p className="mt-0.5 text-xs text-zinc-500">
              Public channel metrics · not counted in SPARK points yet
            </p>
          </div>
          {data.youtube?.handle || data.youtube?.channel_name ? (
            <span className="text-xs text-zinc-400">
              {data.youtube.channel_name} {data.youtube.handle ? `· ${data.youtube.handle}` : ""}
            </span>
          ) : null}
        </div>
        {data.youtube?.connected ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {[
              {
                label: "Subscribers",
                value: formatNumber(data.youtube.subscribers ?? 0),
                sub:
                  data.youtube.subscribers_delta != null
                    ? `${data.youtube.subscribers_delta >= 0 ? "+" : ""}${formatNumber(data.youtube.subscribers_delta)} vs prior snap`
                    : "Live public count",
              },
              {
                label: "Total views",
                value: formatNumber(data.youtube.views ?? 0),
                sub:
                  data.youtube.views_delta != null
                    ? `${data.youtube.views_delta >= 0 ? "+" : ""}${formatNumber(data.youtube.views_delta)} vs prior snap`
                    : "Channel lifetime",
              },
              {
                label: "Videos",
                value: formatNumber(data.youtube.video_count ?? 0),
                sub: "Public uploads tracked",
              },
              {
                label: "Likes (tracked)",
                value: formatNumber(data.youtube.likes ?? 0),
                sub: "From synced videos",
              },
              {
                label: "Comments (tracked)",
                value: formatNumber(data.youtube.comments ?? 0),
                sub: data.youtube.last_synced_at
                  ? `Synced ${new Date(data.youtube.last_synced_at).toLocaleString()}`
                  : "Awaiting sync",
              },
            ].map((k) => (
              <div key={k.label} className="rounded-xl border border-white/[0.04] bg-black/40 p-3">
                <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">{k.label}</div>
                <div className="mt-1 text-xl font-semibold tabular">{k.value}</div>
                <div className="mt-1 text-[11px] text-zinc-500">{k.sub}</div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-zinc-500">
            No YouTube channel linked yet. Ask an admin to connect your channel from Scraping → your profile.
          </p>
        )}
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-500">Streak / Consistency Score</div>
          <div className="mt-3 flex items-end gap-3">
            <div className="text-4xl font-semibold tabular text-[#ff4d00]">{creator.consistency_score}</div>
            <div className="pb-1 text-sm text-zinc-400">/ 100</div>
          </div>
          <ProgressBar className="mt-4" value={creator.consistency_score} color="#ff4d00" />
          <p className="mt-3 text-sm font-medium text-white">Streak: {creator.streak_weeks}</p>
          <p className="mt-1 text-xs text-zinc-500">{creator.posts_7d} posts in the last 7 days</p>
          {creator.points_breakdown && (
            <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-zinc-400 sm:grid-cols-4">
              <div>Consis. {creator.points_breakdown.consistency ?? 0}</div>
              <div>Perf. {creator.points_breakdown.performance ?? 0}</div>
              <div>Growth {creator.points_breakdown.growth ?? 0}</div>
              {(creator.points_breakdown.collaborations ?? 0) > 0 && (
                <div>Collab {creator.points_breakdown.collaborations}</div>
              )}
              {(creator.points_breakdown.revenue ?? 0) > 0 && (
                <div>Rev {creator.points_breakdown.revenue}</div>
              )}
              {(creator.points_breakdown.recognition ?? 0) > 0 && (
                <div>Recog {creator.points_breakdown.recognition}</div>
              )}
              {(creator.points_breakdown.participation ?? 0) > 0 && (
                <div>Part. {creator.points_breakdown.participation}</div>
              )}
              {(creator.points_breakdown.monthly_bonuses ?? 0) > 0 && (
                <div>Bonus {creator.points_breakdown.monthly_bonuses}</div>
              )}
              {(creator.points_breakdown.bonus ?? 0) > 0 && (
                <div>Manual {creator.points_breakdown.bonus}</div>
              )}
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
            <Link href="/student-leaderboard" className="text-[11px] text-[#ff4d00] hover:underline">
              Full board →
            </Link>
          </div>
          <div className="space-y-3">
            {topFive.map((row) => (
              <div key={row.id} className="flex items-center gap-3">
                <span className="w-5 text-xs tabular text-zinc-500">{String(row.rank).padStart(2, "0")}</span>
                <SparkAvatar initials={row.initials} size="sm" accent={row.rank === 1} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{row.name}</div>
                  <div className="text-[11px] text-zinc-500">
                    {formatNumber(row.points)} pts · {formatNumber(row.followers)} followers
                  </div>
                  <ProgressBar className="mt-1.5" value={row.points} max={Math.max(creator.points, topFive[0]?.points || 1)} color="#ff3b30" />
                </div>
              </div>
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

      {/* Personal analytics — same data the admin sees for this student */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ["Following", formatNumber(data.profile?.following ?? 0)],
          ["Posts scraped", formatNumber((data.recent_posts || []).length)],
          ["Engagement", `${creator.engagement}%`],
          ["Last scraped", data.profile?.last_scraped_at ? new Date(data.profile.last_scraped_at).toLocaleDateString() : "—"],
        ].map(([l, v]) => (
          <div key={l} className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
            <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">{l}</div>
            <div className="mt-2 text-lg font-semibold tabular">{v}</div>
          </div>
        ))}
      </div>

      {!!Object.keys(data.insights || {}).length && (
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <h2 className="text-sm font-semibold">My insights</h2>
          <p className="mt-1 text-xs text-zinc-500">Computed from your scraped Instagram posts.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[
              ["Posts / 7d", String((data.insights as Record<string, unknown>)?.posts_last_7d ?? creator.posts_7d)],
              ["Posts / 30d", String((data.insights as Record<string, unknown>)?.posts_last_30d ?? "—")],
              ["Median likes", formatNumber(Number((data.insights as Record<string, unknown>)?.median_likes ?? 0))],
              ["Max likes", formatNumber(Number((data.insights as Record<string, unknown>)?.max_likes ?? 0))],
              ["Max reel views", formatNumber(Number((data.insights as Record<string, unknown>)?.max_reel_views ?? (data.insights as Record<string, unknown>)?.max_views ?? 0))],
              ["Reels", formatNumber(Number((data.insights as Record<string, unknown>)?.reel_count ?? 0))],
              ["Images", formatNumber(Number((data.insights as Record<string, unknown>)?.image_count ?? 0))],
              ["Video share", `${Number((data.insights as Record<string, unknown>)?.video_share_pct ?? 0)}%`],
            ].map(([l, v]) => (
              <div key={l} className="rounded-xl bg-black/40 p-3">
                <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">{l}</div>
                <div className="mt-1 text-sm font-semibold tabular">{v}</div>
              </div>
            ))}
          </div>
          {!!((data.insights as { top_hashtags?: string[] })?.top_hashtags || []).length && (
            <div className="mt-4 flex flex-wrap gap-2">
              {((data.insights as { top_hashtags?: string[] }).top_hashtags || []).slice(0, 12).map((h) => (
                <span key={h} className="rounded-full bg-zinc-800 px-3 py-1 text-xs">
                  #{h}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
        <h2 className="text-sm font-semibold">My recent posts</h2>
        <p className="mt-1 text-xs text-zinc-500">From live Instagram scrapes on your profile.</p>
        <div className="mt-4 columns-1 gap-3 sm:columns-2 lg:columns-3">
          {(data.recent_posts || []).map((post) => (
            <div key={post.id} className="mb-3 break-inside-avoid rounded-xl border border-white/[0.04] bg-black/40 p-3">
              <div className="text-[10px] uppercase tracking-wide text-zinc-500">{post.media_type}</div>
              <p className="mt-1 text-sm line-clamp-3 text-zinc-300">{post.caption || "Untitled"}</p>
              <div className="mt-2 flex flex-wrap gap-2 text-[11px] tabular text-zinc-500">
                <span>{formatNumber(post.likes)} likes</span>
                <span>{formatNumber(post.comments)} comments</span>
                <span>{formatNumber(post.views)} views</span>
              </div>
              {post.permalink && (
                <a href={post.permalink} target="_blank" rel="noreferrer" className="mt-2 inline-block text-[11px] text-[#ff4d00] hover:underline">
                  Open on Instagram →
                </a>
              )}
            </div>
          ))}
          {!data.recent_posts?.length && <p className="text-sm text-zinc-500">No scraped posts yet — ask an admin to refresh your profile.</p>}
        </div>
      </div>

      {(data.history?.length || 0) > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <h2 className="mb-4 text-sm font-semibold">Growth history</h2>
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-wide text-zinc-500">
                <th className="pb-2 pr-3 font-medium">Date</th>
                <th className="pb-2 pr-3 font-medium">Followers</th>
                <th className="pb-2 pr-3 font-medium">Avg likes</th>
                <th className="pb-2 pr-3 font-medium">Avg views</th>
                <th className="pb-2 font-medium">Growth</th>
              </tr>
            </thead>
            <tbody>
              {(data.history || []).slice(0, 15).map((s) => (
                <tr key={s.id} className="border-b border-white/[0.04]">
                  <td className="py-2 pr-3">{s.snapshot_date}</td>
                  <td className="py-2 pr-3 tabular">{formatNumber(s.followers)}</td>
                  <td className="py-2 pr-3 tabular">{formatNumber(s.avg_likes)}</td>
                  <td className="py-2 pr-3 tabular text-zinc-500">{formatNumber(s.avg_views)}</td>
                  <td className={`py-2 tabular ${s.followers_growth_pct >= 0 ? "text-lime-400" : "text-rose-400"}`}>
                    {s.followers_growth_pct >= 0 ? "+" : ""}
                    {s.followers_growth_pct.toFixed(2)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-wrap gap-3 text-xs text-zinc-500">
        <span>{data.total_participants} creators ranked</span>
        <Link href="/top-10" className="text-[#ff4d00] hover:underline">
          Public Top 10 →
        </Link>
        <Link href="/student-leaderboard" className="hover:text-zinc-300">
          My leaderboard →
        </Link>
      </div>
    </div>
  );
}
