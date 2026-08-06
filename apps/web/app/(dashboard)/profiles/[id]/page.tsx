"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { BadgeCheck, ExternalLink, Pause, RefreshCw, Trash2, AlertCircle } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Avatar } from "@/components/ui/avatar";
import { api, type Profile } from "@/lib/api";
import { studentDetailFields } from "@/lib/student-fields";
import { formatNumber, formatPct, humanizeScrapeError } from "@/lib/utils";
import { waitForProfileScrape } from "@/lib/wait-for-scrape";

type Post = {
  id: string;
  shortcode: string;
  media_type: string;
  caption?: string | null;
  thumbnail_url?: string | null;
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
  reel_posts_with_views?: number;
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
  posts_without_views?: number;
};

const tabs = ["overview", "student", "insights", "posts", "growth", "analytics", "history"] as const;

function statusBadgeClass(status: string) {
  if (status === "failed") return "badge-danger";
  if (status === "active") return "badge-success";
  if (status === "paused") return "badge-warning";
  return "badge-neutral";
}

function ChartTip({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-border bg-white px-3 py-2 shadow-lift text-xs">
      <div className="text-muted">{label}</div>
      <div className="mt-0.5 font-semibold tabular">{formatNumber(payload[0].value)}</div>
    </div>
  );
}

function num(v: unknown, fallback = 0): number {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}

export default function ProfileDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [tab, setTab] = useState<(typeof tabs)[number]>("overview");

  const profileId = Array.isArray(id) ? id[0] : id;

  const profileQ = useQuery({
    queryKey: ["profile", profileId],
    queryFn: () => api<Profile>(`/profiles/${profileId}`),
    enabled: Boolean(profileId),
    placeholderData: (prev) => prev,
  });
  const postsQ = useQuery({
    queryKey: ["posts", profileId],
    queryFn: () => api<Post[]>(`/profiles/${profileId}/posts`),
    enabled: Boolean(profileId) && (tab === "posts" || tab === "overview" || tab === "insights"),
    placeholderData: (prev) => prev,
  });
  const historyQ = useQuery({
    queryKey: ["history", profileId],
    queryFn: () => api<Snapshot[]>(`/profiles/${profileId}/history`),
    enabled: Boolean(profileId) && (tab === "history" || tab === "overview"),
    placeholderData: (prev) => prev,
  });
  const analyticsQ = useQuery({
    queryKey: ["analytics", profileId],
    queryFn: () => api<Analytics>(`/analytics/profiles/${profileId}`),
    enabled: Boolean(profileId) && (tab === "analytics" || tab === "growth" || tab === "overview"),
    placeholderData: (prev) => prev,
  });

  const refresh = useMutation({
    mutationFn: async () => {
      const before = profileQ.data;
      await api(`/profiles/${profileId}/refresh`, { method: "POST" });
      return waitForProfileScrape(profileId, {
        since: before?.last_scraped_at,
        prevFollowers: before?.followers,
        prevPosts: before?.posts_count,
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["profile", profileId] });
      void qc.invalidateQueries({ queryKey: ["posts", profileId] });
      void qc.invalidateQueries({ queryKey: ["history", profileId] });
      void qc.invalidateQueries({ queryKey: ["analytics", profileId] });
      void qc.invalidateQueries({ queryKey: ["overview"] });
      void qc.invalidateQueries({ queryKey: ["profiles"] });
    },
  });

  const pause = useMutation({
    mutationFn: () => api(`/profiles/${profileId}/pause`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["profile", profileId] }),
  });

  const del = useMutation({
    mutationFn: () => api(`/profiles/${profileId}`, { method: "DELETE" }),
    onSuccess: () => router.push("/profiles"),
  });

  const p = profileQ.data;
  // Only show skeleton on the very first load — never unmount the page while refetching.
  if (profileQ.isPending && !p) return <div className="h-48 skeleton" />;
  if (!p) return <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-danger">Profile not found</div>;

  const insights = (p.insights || {}) as Insights;
  const topPost = [...(postsQ.data || [])].sort((a, b) => b.likes - a.likes)[0];
  const latestPost = postsQ.data?.[0];

  return (
    <div className="space-y-7">
      {p.status === "failed" && (
        <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-danger">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Last scrape failed</div>
            <p className="mt-1 text-danger/90">{humanizeScrapeError(p.last_error)}</p>
            <p className="mt-2 text-xs text-danger/70">Click Refresh to re-queue a live scrape. Usable data is saved whenever Instagram responds.</p>
          </div>
        </div>
      )}

      <Card padding="lg" className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-y-0 right-0 w-1/3 bg-gradient-to-l from-accent/[0.04] to-transparent" />
        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex gap-5">
            <Avatar name={p.username} size="xl" className="rounded-2xl shadow-lift ring-4 ring-white" />
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-[family-name:var(--font-display)] text-xl font-semibold tracking-tight">@{p.username}</h2>
                {p.is_verified && (
                  <span className="badge-accent inline-flex items-center gap-1">
                    <BadgeCheck size={12} /> Verified
                  </span>
                )}
                {p.is_business && <span className="badge-neutral">Business</span>}
                {p.is_private && <span className="badge-neutral">Private</span>}
                {p.category && <span className="badge-neutral">{p.category}</span>}
                <span className={statusBadgeClass(p.status)}>{p.status}</span>
              </div>
              {p.bio && <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted line-clamp-3">{p.bio}</p>}
              {p.student?.full_name && (
                <p className="mt-2 text-sm text-muted">
                  <span className="font-medium text-fg">{p.student.full_name}</span>
                  {p.student.university ? ` · ${p.student.university}` : ""}
                  {p.student.student_id ? ` · ${p.student.student_id}` : ""}
                </p>
              )}
              <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
                <div><span className="font-semibold tabular">{formatNumber(p.followers)}</span> <span className="text-muted">followers</span></div>
                <div><span className="font-semibold tabular">{formatNumber(p.following)}</span> <span className="text-muted">following</span></div>
                <div><span className="font-semibold tabular">{formatNumber(p.posts_count)}</span> <span className="text-muted">posts</span></div>
                <div><span className="font-semibold tabular">{(p.follower_following_ratio || 0).toFixed(2)}</span> <span className="text-muted">f/f ratio</span></div>
                <div className={`font-semibold tabular ${p.growth_pct_today >= 0 ? "text-success" : "text-danger"}`}>
                  {formatPct(p.growth_pct_today)} today
                </div>
              </div>
              {p.website && (
                <a href={p.website} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-sm text-accent hover:underline">
                  {p.website} <ExternalLink size={12} />
                </a>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => refresh.mutate()} disabled={refresh.isPending}>
                <RefreshCw size={15} className={refresh.isPending ? "animate-spin" : ""} />
                {refresh.isPending ? "Scraping…" : "Refresh"}
              </Button>
              <Button variant="secondary" onClick={() => pause.mutate()}>
                <Pause size={15} /> Pause
              </Button>
              <Button variant="danger" onClick={() => del.mutate()}>
                <Trash2 size={15} /> Delete
              </Button>
            </div>
            {refresh.isError && (
              <p className="max-w-xs text-right text-xs text-danger">
                {(refresh.error as Error)?.message || "Refresh request failed"}
              </p>
            )}
            {refresh.isSuccess && !refresh.isError && (
              <p className="max-w-xs text-right text-xs text-muted">
                Scrape finished — Insights and posts are updated.
              </p>
            )}
          </div>
        </div>
      </Card>

      <div className="flex gap-1 overflow-x-auto rounded-xl border border-border bg-white p-1 shadow-soft">
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`relative rounded-lg px-4 py-2 text-sm capitalize transition ${
              tab === t ? "bg-fg text-white shadow-soft" : "text-muted hover:text-fg hover:bg-slate-50"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "student" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card padding="lg">
            <div className="mb-4 text-sm font-semibold">SPARK registration</div>
            {p.student && Object.keys(p.student).length ? (
              <dl className="grid gap-3 text-sm">
                {studentDetailFields(p.student).map(([label, value]) => (
                  <div key={label} className="grid grid-cols-[160px_minmax(0,1fr)] gap-3 border-b border-border/60 pb-2 last:border-0">
                    <dt className="text-muted">{label}</dt>
                    <dd className="break-words font-medium">
                      {label === "YouTube status" ? (
                        <span className="badge-neutral">{value || "Coming soon"}</span>
                      ) : value ? (
                        String(value)
                      ) : (
                        "—"
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-sm text-muted">No registration sheet data for this profile yet.</p>
            )}
          </Card>
          <Card padding="lg">
            <div className="mb-4 text-sm font-semibold">Why join Spark?</div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted">
              {p.student?.why_join_spark || "—"}
            </p>
            <div className="mt-6 mb-2 text-sm font-semibold">Content interest</div>
            <p className="text-sm text-muted">{p.student?.content_interest || "—"}</p>
          </Card>
        </div>
      )}

      {tab === "overview" && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2 h-80" padding="lg">
            <div className="mb-3 text-sm font-semibold">Follower graph</div>
            <div className="h-[85%] min-h-[220px]">
              {(analyticsQ.data?.followers_trend?.length ?? 0) > 0 ? (
                <ResponsiveContainer width="100%" height="100%" debounce={50}>
                  <AreaChart data={analyticsQ.data!.followers_trend}>
                    <defs>
                      <linearGradient id="fg" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#4F46E5" stopOpacity={0.25} />
                        <stop offset="100%" stopColor="#4F46E5" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="rgba(15,23,42,0.06)" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} width={48} />
                    <Tooltip content={<ChartTip />} />
                    <Area type="monotone" dataKey="value" stroke="#4F46E5" fill="url(#fg)" strokeWidth={2.5} isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-muted">
                  {analyticsQ.isFetching ? "Loading trend…" : "No follower history yet — refresh to start tracking."}
                </div>
              )}
            </div>
          </Card>
          <div className="space-y-4">
            {[
              ["Avg likes", formatNumber(p.avg_likes)],
              ["Avg views", formatNumber(p.avg_views)],
              ["Avg comments", formatNumber(p.avg_comments)],
              ["Engagement", `${p.engagement_rate.toFixed(2)}%`],
            ].map(([label, value]) => (
              <Card key={label} hover>
                <div className="eyebrow">{label}</div>
                <div className="stat-value mt-2 text-[1.35rem]">{value}</div>
              </Card>
            ))}
          </div>
          <Card hover padding="none" className="overflow-hidden">
            <div className="border-b border-border px-5 py-3 text-sm font-semibold">Top performing post</div>
            {topPost ? (
              <div>
                <div className="flex aspect-[4/3] w-full items-center justify-center bg-stone-100 text-sm font-medium capitalize text-stone-500">
                  {topPost.media_type || "post"}
                </div>
                <div className="space-y-2 p-5">
                  <p className="text-sm text-muted line-clamp-2">{topPost.caption}</p>
                  <div className="text-sm font-medium tabular">
                    {formatNumber(topPost.likes)} likes · {formatNumber(topPost.comments)} comments
                  </div>
                </div>
              </div>
            ) : (
              <p className="p-5 text-sm text-muted">No posts yet — refresh to scrape.</p>
            )}
          </Card>
          <Card hover padding="none" className="overflow-hidden">
            <div className="border-b border-border px-5 py-3 text-sm font-semibold">Latest post</div>
            {latestPost ? (
              <div>
                <div className="flex aspect-[4/3] w-full items-center justify-center bg-stone-100 text-sm font-medium capitalize text-stone-500">
                  {latestPost.media_type || "post"}
                </div>
                <div className="p-5">
                  <p className="text-sm text-muted line-clamp-2">{latestPost.caption}</p>
                </div>
              </div>
            ) : (
              <p className="p-5 text-sm text-muted">No posts yet.</p>
            )}
          </Card>
          <Card hover>
            <div className="eyebrow">Growth summary</div>
            <div className={`stat-value mt-3 ${p.growth_pct_today >= 0 ? "text-success" : "text-danger"}`}>
              {formatPct(p.growth_pct_today)}
            </div>
            <p className="mt-2 text-sm text-muted">Compared to previous scrape snapshot.</p>
          </Card>
        </div>
      )}

      {tab === "insights" && (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              ["Scraped posts", formatNumber(num(insights.sampled_posts))],
              ["Posts / 7d", formatNumber(num(insights.posts_last_7d))],
              ["Posts / 30d", formatNumber(num(insights.posts_last_30d))],
              ["Posting / week", `${num(insights.posting_frequency_per_week)}`],
              ["Median likes", formatNumber(num(insights.median_likes))],
              ["Max likes", formatNumber(num(insights.max_likes))],
              ["Max reel views", formatNumber(num(insights.max_reel_views || insights.max_views))],
              ["Avg reel views", formatNumber(num(insights.avg_reel_views || insights.avg_views))],
              ["Total reel views", formatNumber(num(insights.total_reel_views || insights.total_views_sampled))],
              ["Min likes", formatNumber(num(insights.min_likes))],
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
              ["Reel/video views total", formatNumber(num(insights.total_views_sampled))],
              ["Posts with views", `${num(insights.posts_with_views)} / ${num(insights.sampled_posts)}`],
              ["Avg caption length", `${num(insights.avg_caption_length)}`],
              ["Highlights", formatNumber(p.highlight_reel_count || 0)],
              ["Last post", insights.last_post_at ? new Date(insights.last_post_at).toLocaleDateString() : "—"],
              ["Profile posts total", formatNumber(p.posts_count)],
            ].map(([label, value]) => (
              <Card key={String(label)} hover>
                <div className="eyebrow">{label}</div>
                <div className="mt-2 text-xl font-semibold tracking-tight tabular">{value}</div>
              </Card>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card padding="lg">
              <div className="mb-3 text-sm font-semibold">Top hashtags (from captions)</div>
              <div className="flex flex-wrap gap-2">
                {(insights.top_hashtags || []).length ? (
                  insights.top_hashtags!.map((h) => (
                    <span key={h} className="rounded-full bg-stone-100 px-3 py-1 text-xs font-medium text-stone-700">
                      #{h}
                    </span>
                  ))
                ) : (
                  <p className="text-sm text-muted">No hashtags in sampled captions. Refresh for latest posts.</p>
                )}
              </div>
            </Card>
            <Card padding="lg">
              <div className="mb-3 text-sm font-semibold">Top mentions</div>
              <div className="flex flex-wrap gap-2">
                {(insights.top_mentions || []).length ? (
                  insights.top_mentions!.map((m) => (
                    <span key={m} className="rounded-full bg-stone-100 px-3 py-1 text-xs font-medium text-stone-700">
                      @{m}
                    </span>
                  ))
                ) : (
                  <p className="text-sm text-muted">No @mentions in sampled captions.</p>
                )}
              </div>
            </Card>
            <Card padding="lg">
              <div className="mb-2 text-sm font-semibold">Best sampled post</div>
              {insights.best_post_shortcode ? (
                <a
                  href={`https://www.instagram.com/p/${insights.best_post_shortcode}/`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-accent hover:underline"
                >
                  /p/{insights.best_post_shortcode}/ · {formatNumber(num(insights.best_post_likes))} likes
                </a>
              ) : (
                <p className="text-sm text-muted">Refresh to compute.</p>
              )}
            </Card>
            <Card padding="lg">
              <div className="mb-2 text-sm font-semibold">Lowest sampled post</div>
              {insights.worst_post_shortcode ? (
                <a
                  href={`https://www.instagram.com/p/${insights.worst_post_shortcode}/`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-accent hover:underline"
                >
                  /p/{insights.worst_post_shortcode}/ · {formatNumber(num(insights.worst_post_likes))} likes
                </a>
              ) : (
                <p className="text-sm text-muted">Refresh to compute.</p>
              )}
            </Card>
          </div>
          {!Object.keys(insights).length && (
            <p className="text-sm text-muted">No insights yet — click Refresh to scrape exact post metrics.</p>
          )}
          <p className="text-xs text-muted leading-relaxed">
            Scraped posts are every public post we pulled for this profile (paginated beyond Instagram’s first page).
            Profile posts total is Instagram’s lifetime count. Metrics (avg likes, hashtags, etc.) use the scraped set.
            Views are reel/video play counts only — photos/carousels usually have no public view field.
            Private profiles and Instagram blocks can stop pagination early; use Refresh again or set SCRAPE_PROXY_URL.
          </p>
        </div>
      )}

      {tab === "posts" && (
        <div className="columns-1 gap-4 sm:columns-2 lg:columns-3">
          {(postsQ.data || []).map((post) => (
            <div
              key={post.id}
              className="mb-4 break-inside-avoid overflow-hidden rounded-2xl border border-border bg-white shadow-soft transition duration-200 hover:-translate-y-0.5 hover:shadow-lift"
            >
              <div className="flex h-28 items-center justify-center bg-stone-100 text-sm font-medium capitalize text-stone-500">
                {post.media_type || "post"}
              </div>
              <div className="space-y-2.5 p-4">
                <p className="text-sm leading-relaxed line-clamp-3">{post.caption || "Untitled post"}</p>
                <div className="flex flex-wrap gap-3 text-xs text-muted tabular">
                  <span>{formatNumber(post.likes)} likes</span>
                  <span>{formatNumber(post.comments)} comments</span>
                  <span>{formatNumber(post.views)} views</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted">{post.posted_at ? new Date(post.posted_at).toLocaleDateString() : "—"}</span>
                  {post.permalink && (
                    <a href={post.permalink} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline">
                      Open <ExternalLink size={11} />
                    </a>
                  )}
                </div>
              </div>
            </div>
          ))}
          {!postsQ.data?.length && <p className="text-sm text-muted">No posts stored yet. Click Refresh.</p>}
        </div>
      )}

      {tab === "growth" && (
        <Card className="h-80" padding="lg">
          <div className="mb-3 text-sm font-semibold">Followers trend</div>
          <div className="h-[85%] min-h-[220px]">
            {(analyticsQ.data?.followers_trend?.length ?? 0) > 0 ? (
              <ResponsiveContainer width="100%" height="100%" debounce={50}>
                <AreaChart data={analyticsQ.data!.followers_trend}>
                  <CartesianGrid stroke="rgba(15,23,42,0.06)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                  <Tooltip content={<ChartTip />} />
                  <Area type="monotone" dataKey="value" stroke="#059669" fill="#ECFDF5" strokeWidth={2.5} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted">
                {analyticsQ.isFetching ? "Loading trend…" : "No follower history yet."}
              </div>
            )}
          </div>
        </Card>
      )}

      {tab === "analytics" && analyticsQ.data && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {[
            ["Posting frequency", `${analyticsQ.data.posting_frequency}/wk`],
            ["Avg engagement", `${analyticsQ.data.average_engagement.toFixed(2)}%`],
            ["Best day", analyticsQ.data.best_posting_day || "—"],
            ["Best hour", analyticsQ.data.best_posting_hour ?? "—"],
          ].map(([label, value]) => (
            <Card key={label} hover>
              <div className="eyebrow">{label}</div>
              <div className="stat-value mt-2 text-[1.5rem]">{value}</div>
            </Card>
          ))}
          {(["views_trend", "likes_trend", "comments_trend"] as const).map((key) => (
            <Card key={key} className="md:col-span-2 h-64" padding="lg">
              <div className="mb-2 text-sm font-semibold capitalize">{key.replace("_", " ")}</div>
              <div className="h-[85%] min-h-[180px]">
                {(analyticsQ.data![key]?.length ?? 0) > 0 ? (
                  <ResponsiveContainer width="100%" height="100%" debounce={50}>
                    <AreaChart data={analyticsQ.data![key]}>
                      <CartesianGrid stroke="rgba(15,23,42,0.06)" vertical={false} />
                      <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                      <Tooltip content={<ChartTip />} />
                      <Area type="monotone" dataKey="value" stroke="#4F46E5" fill="#EEF2FF" strokeWidth={2} isAnimationActive={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-muted">No data yet.</div>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      {tab === "history" && (
        <Card padding="lg">
          <div className="overflow-x-auto">
            <table className="table-premium">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Followers</th>
                  <th>Following</th>
                  <th>Posts</th>
                  <th>Avg likes</th>
                  <th>Avg views</th>
                  <th>Growth</th>
                </tr>
              </thead>
              <tbody>
                {(historyQ.data || []).map((s) => (
                  <tr key={s.id}>
                    <td className="font-medium">{s.snapshot_date}</td>
                    <td className="tabular">{formatNumber(s.followers)}</td>
                    <td className="tabular text-muted">{formatNumber(s.following)}</td>
                    <td className="tabular text-muted">{formatNumber(s.posts_count)}</td>
                    <td className="tabular">{formatNumber(s.avg_likes)}</td>
                    <td className="tabular text-muted">{formatNumber(s.avg_views)}</td>
                    <td className={`tabular font-medium ${s.followers_growth_pct >= 0 ? "text-success" : "text-danger"}`}>
                      {formatPct(s.followers_growth_pct)}
                    </td>
                  </tr>
                ))}
                {!historyQ.data?.length && (
                  <tr>
                    <td colSpan={7} className="py-10 text-center text-muted">No snapshots yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
