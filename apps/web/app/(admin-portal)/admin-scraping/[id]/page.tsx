"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AlertCircle, ExternalLink, Pause, RefreshCw, Trash2 } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type Profile } from "@/lib/api";
import { studentDetailFieldsExtra } from "@/lib/student-fields";
import { cn, formatNumber, formatPct, humanizeScrapeError } from "@/lib/utils";

type Post = {
  id: string;
  shortcode: string;
  media_type: string;
  caption?: string | null;
  permalink?: string | null;
  likes: number;
  comments: number;
  views: number;
  posted_at?: string | null;
};

type Snapshot = {
  id: string;
  snapshot_date: string;
  followers: number;
  following: number;
  posts_count: number;
  avg_likes: number;
  avg_views: number;
  engagement_rate: number;
  followers_growth: number;
  followers_growth_pct: number;
};

type Analytics = {
  followers_trend: { date: string; value: number }[];
  views_trend: { date: string; value: number }[];
  likes_trend: { date: string; value: number }[];
  comments_trend: { date: string; value: number }[];
  posting_frequency: number;
  average_engagement: number;
  best_posting_day?: string | null;
  best_posting_hour?: number | null;
  growth_pct: number;
};

type Insights = {
  avg_likes?: number;
  avg_comments?: number;
  avg_views?: number;
  avg_reel_views?: number;
  total_reel_views?: number;
  max_reel_views?: number;
  engagement_rate?: number;
  like_follower_ratio?: number;
  comment_follower_ratio?: number;
  sampled_posts?: number;
  image_count?: number;
  video_count?: number;
  reel_count?: number;
  carousel_count?: number;
  posts_last_7d?: number;
  posts_last_30d?: number;
  posting_frequency_per_week?: number;
  best_post_shortcode?: string | null;
  best_post_likes?: number;
  worst_post_shortcode?: string | null;
  worst_post_likes?: number;
  last_post_at?: string | null;
  top_hashtags?: string[];
  top_mentions?: string[];
  total_likes_sampled?: number;
  total_comments_sampled?: number;
  total_views_sampled?: number;
  avg_caption_length?: number;
  comments_to_likes_ratio?: number;
  video_share_pct?: number;
  median_likes?: number;
  max_likes?: number;
  max_views?: number;
  min_likes?: number;
  posts_with_views?: number;
};

const tabs = ["overview", "student", "insights", "posts", "growth", "analytics", "history"] as const;

function ChartTip({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-white/10 bg-[#1a1a1a] px-3 py-2 text-xs shadow-lg">
      <div className="text-zinc-500">{label}</div>
      <div className="mt-0.5 font-semibold tabular text-white">{formatNumber(payload[0].value)}</div>
    </div>
  );
}

function num(v: unknown, fallback = 0): number {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}

export default function AdminCreatorDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [tab, setTab] = useState<(typeof tabs)[number]>("overview");
  const profileId = Array.isArray(id) ? id[0] : id;

  const profileQ = useQuery({
    queryKey: ["profile", profileId],
    queryFn: () => api<Profile>(`/profiles/${profileId}`),
    enabled: Boolean(profileId),
  });
  const postsQ = useQuery({
    queryKey: ["posts", profileId],
    queryFn: () => api<Post[]>(`/profiles/${profileId}/posts`),
    enabled: Boolean(profileId) && (tab === "posts" || tab === "overview" || tab === "insights"),
  });
  const historyQ = useQuery({
    queryKey: ["history", profileId],
    queryFn: () => api<Snapshot[]>(`/profiles/${profileId}/history`),
    enabled: Boolean(profileId) && (tab === "history" || tab === "overview"),
  });
  const analyticsQ = useQuery({
    queryKey: ["analytics", profileId],
    queryFn: () => api<Analytics>(`/analytics/profiles/${profileId}`),
    enabled: Boolean(profileId) && (tab === "analytics" || tab === "growth" || tab === "overview"),
  });

  const [refreshError, setRefreshError] = useState("");
  const refresh = useMutation({
    mutationFn: () => api(`/profiles/${profileId}/refresh`, { method: "POST" }),
    onSuccess: () => {
      setRefreshError("");
      void qc.invalidateQueries({ queryKey: ["profile", profileId] });
      void qc.invalidateQueries({ queryKey: ["posts", profileId] });
      void qc.invalidateQueries({ queryKey: ["history", profileId] });
      void qc.invalidateQueries({ queryKey: ["analytics", profileId] });
      void qc.invalidateQueries({ queryKey: ["spark"] });
      void qc.invalidateQueries({ queryKey: ["profiles"] });
    },
    onError: (e: Error) => setRefreshError(humanizeScrapeError(e.message) || e.message),
  });
  const pause = useMutation({
    mutationFn: () => api(`/profiles/${profileId}/pause`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["profile", profileId] }),
  });
  const del = useMutation({
    mutationFn: () => api(`/profiles/${profileId}`, { method: "DELETE" }),
    onSuccess: () => router.push("/admin-scraping"),
  });

  if (profileQ.isPending && !profileQ.data) return <div className="h-48 animate-pulse rounded-2xl bg-zinc-900" />;
  if (profileQ.error || !profileQ.data) {
    return (
      <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
        {(profileQ.error as Error)?.message || "Not found"}
      </div>
    );
  }

  const p = profileQ.data;
  const insights = (p.insights || {}) as Insights;
  const topPost = [...(postsQ.data || [])].sort((a, b) => b.likes - a.likes)[0];
  const latestPost = postsQ.data?.[0];

  return (
    <div className="space-y-6">
      {p.status === "failed" && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Last scrape failed</div>
            <p className="mt-1 opacity-90">{humanizeScrapeError(p.last_error) || "Unknown error — try Refresh."}</p>
          </div>
        </div>
      )}
      {refreshError && (
        <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {refreshError}
        </div>
      )}

      <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <Link href="/admin-scraping" className="text-xs text-zinc-500 hover:text-zinc-300">
              ← Scraping
            </Link>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold">@{p.username}</h1>
              {p.is_verified && <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] text-sky-300">Verified</span>}
              {p.is_business && <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400">Business</span>}
              {p.is_private && <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] text-amber-300">Private</span>}
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-[10px] capitalize",
                  p.status === "failed" ? "bg-rose-500/15 text-rose-400" : "bg-emerald-500/15 text-emerald-400"
                )}
              >
                {p.status}
              </span>
            </div>
            {p.bio && <p className="mt-2 max-w-2xl text-sm text-zinc-400 line-clamp-3">{p.bio}</p>}
            {p.student?.full_name && (
              <p className="mt-2 text-sm text-zinc-400">
                <span className="font-medium text-zinc-200">{p.student.full_name}</span>
                {p.student.university ? ` · ${p.student.university}` : ""}
                {p.student.student_id ? ` · ${p.student.student_id}` : ""}
              </p>
            )}
            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm">
              <div>
                <span className="font-semibold tabular">{formatNumber(p.followers)}</span>{" "}
                <span className="text-zinc-500">followers</span>
              </div>
              <div>
                <span className="font-semibold tabular">{formatNumber(p.following)}</span>{" "}
                <span className="text-zinc-500">following</span>
              </div>
              <div>
                <span className="font-semibold tabular">{formatNumber(p.posts_count)}</span>{" "}
                <span className="text-zinc-500">posts</span>
              </div>
              <div className={cn("font-semibold tabular", p.growth_pct_today >= 0 ? "text-emerald-400" : "text-rose-400")}>
                {formatPct(p.growth_pct_today)} today
              </div>
            </div>
            {p.website && (
              <a href={p.website} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-sm text-[#ff4d00] hover:underline">
                {p.website} <ExternalLink size={12} />
              </a>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={refresh.isPending}
              onClick={() => refresh.mutate()}
              className="inline-flex items-center gap-2 rounded-xl bg-[#ff3b30] px-4 py-2 text-sm font-semibold disabled:opacity-60"
            >
              <RefreshCw size={14} className={refresh.isPending ? "animate-spin" : ""} />
              {refresh.isPending ? "Scraping…" : "Refresh / Scrape"}
            </button>
            <button
              type="button"
              onClick={() => pause.mutate()}
              className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-black/40 px-4 py-2 text-sm"
            >
              <Pause size={14} /> Pause
            </button>
            <button
              type="button"
              onClick={() => {
                if (confirm("Delete this creator profile?")) del.mutate();
              }}
              className="inline-flex items-center gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-2 text-sm text-rose-300"
            >
              <Trash2 size={14} /> Delete
            </button>
          </div>
        </div>
      </div>

      <div className="flex gap-1 overflow-x-auto rounded-xl border border-white/[0.06] bg-[#121212] p-1">
        {tabs.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={cn(
              "rounded-lg px-4 py-2 text-sm capitalize transition",
              tab === t ? "bg-[#ff3b30] text-white" : "text-zinc-400 hover:text-white"
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "student" && (
        <div className="space-y-4">
          <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
            <h2 className="mb-1 text-sm font-semibold">SPARK registration details</h2>
            <p className="mb-4 text-xs text-zinc-500">
              All fields from the registration sheet. Header shows name · campus · student ID only.
            </p>
            {p.student && Object.keys(p.student).length ? (
              <dl className="grid gap-0 sm:grid-cols-2">
                {studentDetailFieldsExtra(p.student).map(([label, value]) => (
                  <div
                    key={label}
                    className="grid grid-cols-[minmax(120px,160px)_minmax(0,1fr)] gap-x-3 gap-y-1 border-b border-white/[0.04] py-3"
                  >
                    <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</dt>
                    <dd className="break-words text-sm font-medium text-zinc-100">
                      {value ? (
                        label.toLowerCase().includes("link") || label.toLowerCase().includes("url") ? (
                          <a
                            href={value.startsWith("http") ? value : undefined}
                            target="_blank"
                            rel="noreferrer"
                            className={value.startsWith("http") ? "text-[#ff3b30] hover:underline" : undefined}
                          >
                            {value}
                          </a>
                        ) : (
                          value
                        )
                      ) : (
                        <span className="text-zinc-600">—</span>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-sm text-zinc-500">
                No registration sheet data yet. Import a sheet from Admin → Import, or add the student with roster fields.
              </p>
            )}
          </div>
          {(p.student?.why_join_spark || p.student?.content_interest) && (
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
                <h2 className="mb-2 text-sm font-semibold">Why join Spark?</h2>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-300">
                  {p.student?.why_join_spark || "—"}
                </p>
              </div>
              <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
                <h2 className="mb-2 text-sm font-semibold">Content interest</h2>
                <p className="text-sm leading-relaxed text-zinc-300">{p.student?.content_interest || "—"}</p>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "overview" && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="h-80 rounded-2xl border border-white/[0.06] bg-[#121212] p-5 lg:col-span-2">
            <div className="mb-3 text-sm font-semibold">Follower graph</div>
            <div className="h-[85%] min-h-[220px]">
              {(analyticsQ.data?.followers_trend?.length ?? 0) > 0 ? (
                <ResponsiveContainer width="100%" height="100%" debounce={50}>
                  <AreaChart data={analyticsQ.data!.followers_trend}>
                    <defs>
                      <linearGradient id="adminFg" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#ff3b30" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#ff3b30" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#71717a" }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fill: "#71717a" }} axisLine={false} tickLine={false} width={48} />
                    <Tooltip content={<ChartTip />} />
                    <Area type="monotone" dataKey="value" stroke="#ff3b30" fill="url(#adminFg)" strokeWidth={2.5} isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-zinc-500">
                  {analyticsQ.isFetching ? "Loading…" : "No follower history yet — refresh to start tracking."}
                </div>
              )}
            </div>
          </div>
          <div className="space-y-3">
            {[
              ["Avg likes", formatNumber(p.avg_likes)],
              ["Avg views", formatNumber(p.avg_views)],
              ["Avg comments", formatNumber(p.avg_comments)],
              ["Engagement", `${p.engagement_rate.toFixed(2)}%`],
            ].map(([label, value]) => (
              <div key={label} className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
                <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">{label}</div>
                <div className="mt-2 text-xl font-semibold tabular">{value}</div>
              </div>
            ))}
          </div>
          <div className="overflow-hidden rounded-2xl border border-white/[0.06] bg-[#121212]">
            <div className="border-b border-white/[0.06] px-4 py-3 text-sm font-semibold">Top performing post</div>
            {topPost ? (
              <div className="p-4">
                <div className="mb-2 text-xs capitalize text-zinc-500">{topPost.media_type}</div>
                <p className="text-sm text-zinc-300 line-clamp-2">{topPost.caption}</p>
                <div className="mt-2 text-sm font-medium tabular">
                  {formatNumber(topPost.likes)} likes · {formatNumber(topPost.comments)} comments
                </div>
              </div>
            ) : (
              <p className="p-4 text-sm text-zinc-500">No posts yet.</p>
            )}
          </div>
          <div className="overflow-hidden rounded-2xl border border-white/[0.06] bg-[#121212]">
            <div className="border-b border-white/[0.06] px-4 py-3 text-sm font-semibold">Latest post</div>
            {latestPost ? (
              <div className="p-4">
                <p className="text-sm text-zinc-300 line-clamp-2">{latestPost.caption}</p>
              </div>
            ) : (
              <p className="p-4 text-sm text-zinc-500">No posts yet.</p>
            )}
          </div>
          <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
            <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">Growth summary</div>
            <div className={cn("mt-2 text-2xl font-semibold tabular", p.growth_pct_today >= 0 ? "text-emerald-400" : "text-rose-400")}>
              {formatPct(p.growth_pct_today)}
            </div>
            <p className="mt-2 text-xs text-zinc-500">Compared to previous scrape snapshot.</p>
          </div>
        </div>
      )}

      {tab === "insights" && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[
              ["Scraped posts", formatNumber(num(insights.sampled_posts))],
              ["Posts / 7d", formatNumber(num(insights.posts_last_7d))],
              ["Posts / 30d", formatNumber(num(insights.posts_last_30d))],
              ["Posting / week", `${num(insights.posting_frequency_per_week)}`],
              ["Median likes", formatNumber(num(insights.median_likes))],
              ["Max likes", formatNumber(num(insights.max_likes))],
              ["Min likes", formatNumber(num(insights.min_likes))],
              ["Max reel views", formatNumber(num(insights.max_reel_views || insights.max_views))],
              ["Avg reel views", formatNumber(num(insights.avg_reel_views || insights.avg_views))],
              ["Total reel views", formatNumber(num(insights.total_reel_views || insights.total_views_sampled))],
              ["Reel/video views total", formatNumber(num(insights.total_views_sampled))],
              ["Like / follower %", `${num(insights.like_follower_ratio).toFixed(3)}%`],
              ["Comment / follower %", `${num(insights.comment_follower_ratio).toFixed(3)}%`],
              ["Comments / likes %", `${num(insights.comments_to_likes_ratio).toFixed(2)}%`],
              ["Video share", `${num(insights.video_share_pct)}%`],
              ["Images", formatNumber(num(insights.image_count))],
              ["Reels", formatNumber(num(insights.reel_count))],
              ["Videos", formatNumber(num(insights.video_count))],
              ["Carousels", formatNumber(num(insights.carousel_count))],
              ["Total likes (scraped)", formatNumber(num(insights.total_likes_sampled))],
              ["Total comments", formatNumber(num(insights.total_comments_sampled))],
              ["Posts with views", `${num(insights.posts_with_views)} / ${num(insights.sampled_posts)}`],
              ["Avg caption length", `${num(insights.avg_caption_length)}`],
              ["Highlights", formatNumber(p.highlight_reel_count || 0)],
              ["Profile posts total", formatNumber(p.posts_count)],
              ["Last post", insights.last_post_at ? new Date(insights.last_post_at).toLocaleDateString() : "—"],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
                <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">{label}</div>
                <div className="mt-2 text-lg font-semibold tabular">{value}</div>
              </div>
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
              <div className="mb-3 text-sm font-semibold">Top hashtags</div>
              <div className="flex flex-wrap gap-2">
                {(insights.top_hashtags || []).length ? (
                  insights.top_hashtags!.map((h) => (
                    <span key={h} className="rounded-full bg-zinc-800 px-3 py-1 text-xs">#{h}</span>
                  ))
                ) : (
                  <p className="text-sm text-zinc-500">No hashtags yet.</p>
                )}
              </div>
            </div>
            <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
              <div className="mb-3 text-sm font-semibold">Top mentions</div>
              <div className="flex flex-wrap gap-2">
                {(insights.top_mentions || []).length ? (
                  insights.top_mentions!.map((m) => (
                    <span key={m} className="rounded-full bg-zinc-800 px-3 py-1 text-xs">@{m}</span>
                  ))
                ) : (
                  <p className="text-sm text-zinc-500">No mentions yet.</p>
                )}
              </div>
            </div>
            <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
              <div className="mb-2 text-sm font-semibold">Best sampled post</div>
              {insights.best_post_shortcode ? (
                <a
                  href={`https://www.instagram.com/p/${insights.best_post_shortcode}/`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-[#ff4d00] hover:underline"
                >
                  /p/{insights.best_post_shortcode}/ · {formatNumber(num(insights.best_post_likes))} likes
                </a>
              ) : (
                <p className="text-sm text-zinc-500">Refresh to compute.</p>
              )}
            </div>
            <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
              <div className="mb-2 text-sm font-semibold">Lowest sampled post</div>
              {insights.worst_post_shortcode ? (
                <a
                  href={`https://www.instagram.com/p/${insights.worst_post_shortcode}/`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-[#ff4d00] hover:underline"
                >
                  /p/{insights.worst_post_shortcode}/ · {formatNumber(num(insights.worst_post_likes))} likes
                </a>
              ) : (
                <p className="text-sm text-zinc-500">Refresh to compute.</p>
              )}
            </div>
          </div>
          <p className="text-xs leading-relaxed text-zinc-500">
            Scraped posts are every public post we pulled for this profile. Profile posts total is Instagram’s lifetime
            count. Views are reel/video play counts only — photos/carousels usually have no public view field.
          </p>
        </div>
      )}

      {tab === "posts" && (
        <div className="columns-1 gap-4 sm:columns-2 lg:columns-3">
          {(postsQ.data || []).map((post) => (
            <div key={post.id} className="mb-4 break-inside-avoid overflow-hidden rounded-2xl border border-white/[0.06] bg-[#121212]">
              <div className="flex h-20 items-center justify-center bg-black/40 text-sm capitalize text-zinc-500">
                {post.media_type || "post"}
              </div>
              <div className="space-y-2 p-4">
                <p className="text-sm line-clamp-3">{post.caption || "Untitled"}</p>
                <div className="flex flex-wrap gap-3 text-xs tabular text-zinc-500">
                  <span>{formatNumber(post.likes)} likes</span>
                  <span>{formatNumber(post.comments)} comments</span>
                  <span>{formatNumber(post.views)} views</span>
                </div>
                <div className="flex items-center justify-between text-xs text-zinc-500">
                  <span>{post.posted_at ? new Date(post.posted_at).toLocaleDateString() : "—"}</span>
                  {post.permalink && (
                    <a href={post.permalink} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[#ff4d00] hover:underline">
                      Open <ExternalLink size={11} />
                    </a>
                  )}
                </div>
              </div>
            </div>
          ))}
          {!postsQ.data?.length && <p className="text-sm text-zinc-500">No posts stored yet. Click Refresh.</p>}
        </div>
      )}

      {tab === "growth" && (
        <div className="h-80 rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="mb-3 text-sm font-semibold">Followers trend</div>
          <div className="h-[85%] min-h-[220px]">
            {(analyticsQ.data?.followers_trend?.length ?? 0) > 0 ? (
              <ResponsiveContainer width="100%" height="100%" debounce={50}>
                <AreaChart data={analyticsQ.data!.followers_trend}>
                  <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#71717a" }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: "#71717a" }} axisLine={false} tickLine={false} />
                  <Tooltip content={<ChartTip />} />
                  <Area type="monotone" dataKey="value" stroke="#22c55e" fill="#22c55e22" strokeWidth={2.5} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-zinc-500">No follower history yet.</div>
            )}
          </div>
        </div>
      )}

      {tab === "analytics" && analyticsQ.data && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {[
            ["Posting frequency", `${analyticsQ.data.posting_frequency}/wk`],
            ["Avg engagement", `${analyticsQ.data.average_engagement.toFixed(2)}%`],
            ["Best day", analyticsQ.data.best_posting_day || "—"],
            ["Best hour", analyticsQ.data.best_posting_hour ?? "—"],
          ].map(([label, value]) => (
            <div key={label} className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
              <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">{label}</div>
              <div className="mt-2 text-xl font-semibold tabular">{value}</div>
            </div>
          ))}
          {(["views_trend", "likes_trend", "comments_trend"] as const).map((key) => (
            <div key={key} className="h-64 rounded-2xl border border-white/[0.06] bg-[#121212] p-5 md:col-span-2">
              <div className="mb-2 text-sm font-semibold capitalize">{key.replace("_", " ")}</div>
              <div className="h-[85%] min-h-[180px]">
                {(analyticsQ.data![key]?.length ?? 0) > 0 ? (
                  <ResponsiveContainer width="100%" height="100%" debounce={50}>
                    <AreaChart data={analyticsQ.data![key]}>
                      <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
                      <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#71717a" }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 11, fill: "#71717a" }} axisLine={false} tickLine={false} />
                      <Tooltip content={<ChartTip />} />
                      <Area type="monotone" dataKey="value" stroke="#ff4d00" fill="#ff4d0018" strokeWidth={2} isAnimationActive={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-zinc-500">No data yet.</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "history" && (
        <div className="overflow-x-auto rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-wide text-zinc-500">
                <th className="pb-3 pr-3 font-medium">Date</th>
                <th className="pb-3 pr-3 font-medium">Followers</th>
                <th className="pb-3 pr-3 font-medium">Following</th>
                <th className="pb-3 pr-3 font-medium">Posts</th>
                <th className="pb-3 pr-3 font-medium">Avg likes</th>
                <th className="pb-3 pr-3 font-medium">Avg views</th>
                <th className="pb-3 font-medium">Growth</th>
              </tr>
            </thead>
            <tbody>
              {(historyQ.data || []).map((s) => (
                <tr key={s.id} className="border-b border-white/[0.04]">
                  <td className="py-2.5 pr-3 font-medium">{s.snapshot_date}</td>
                  <td className="py-2.5 pr-3 tabular">{formatNumber(s.followers)}</td>
                  <td className="py-2.5 pr-3 tabular text-zinc-500">{formatNumber(s.following)}</td>
                  <td className="py-2.5 pr-3 tabular text-zinc-500">{formatNumber(s.posts_count)}</td>
                  <td className="py-2.5 pr-3 tabular">{formatNumber(s.avg_likes)}</td>
                  <td className="py-2.5 pr-3 tabular text-zinc-500">{formatNumber(s.avg_views)}</td>
                  <td className={cn("py-2.5 tabular font-medium", s.followers_growth_pct >= 0 ? "text-emerald-400" : "text-rose-400")}>
                    {formatPct(s.followers_growth_pct)}
                  </td>
                </tr>
              ))}
              {!historyQ.data?.length && (
                <tr>
                  <td colSpan={7} className="py-10 text-center text-zinc-500">
                    No snapshots yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
