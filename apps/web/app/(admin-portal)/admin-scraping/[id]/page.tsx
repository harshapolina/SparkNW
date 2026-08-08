"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
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
import {
  cn,
  formatBaselineDay,
  formatNumber,
  formatPct,
  formatSignedNumber,
  humanizeScrapeError,
} from "@/lib/utils";
import { ScrapeProgressCard } from "@/components/scrape-progress";
import { ProgrammeWindowNote } from "@/components/programme-window-note";
import {
  EditableInstagramLink,
  normalizeIgDraft,
  profileIgHref,
} from "@/components/editable-instagram-link";
import { type ScrapeProgress } from "@/lib/scrape-progress";
import { formatScrapeProgress, waitForProfileScrape } from "@/lib/wait-for-scrape";
import { adminScrapingListHref } from "@/lib/admin-scraping-list-state";

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
  window_from?: string | null;
  window_to?: string | null;
  cohort_start?: string | null;
  posts_stored?: number;
  posts_missing_dates?: number;
  posts_in_window?: number;
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
    refetchInterval: (q) => (q.state.data?.scrape_progress?.active ? 2500 : false),
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
  const [scrapingNote, setScrapingNote] = useState("");
  const [liveProgress, setLiveProgress] = useState<ScrapeProgress | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [igDraft, setIgDraft] = useState("");
  const [igEditing, setIgEditing] = useState(false);
  const [igError, setIgError] = useState("");

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!profileQ.data || igEditing) return;
    setIgDraft(profileIgHref(profileQ.data.username, profileQ.data.profile_url));
    setIgError("");
  }, [profileQ.data, igEditing]);

  const igHref = profileQ.data
    ? profileIgHref(profileQ.data.username, profileQ.data.profile_url)
    : "";
  const igDirty =
    Boolean(igDraft.trim()) &&
    normalizeIgDraft(igDraft) !== normalizeIgDraft(igHref || igDraft);

  const saveIgLink = useMutation({
    mutationFn: async (url: string) => {
      return api<Profile>(`/profiles/${profileId}`, {
        method: "PATCH",
        body: JSON.stringify({ url }),
      });
    },
    onSuccess: (updated) => {
      setIgError("");
      setIgEditing(false);
      setIgDraft(profileIgHref(updated.username, updated.profile_url));
      qc.setQueryData(["profile", profileId], updated);
      void qc.invalidateQueries({ queryKey: ["profile", profileId] });
      void qc.invalidateQueries({ queryKey: ["profiles"] });
    },
    onError: (err) => {
      setIgError((err as Error).message || "Could not update Instagram link");
    },
  });

  const ensureIgSaved = async () => {
    if (!igDirty) return profileQ.data;
    return saveIgLink.mutateAsync(igDraft.trim());
  };

  const refresh = useMutation({
    mutationFn: async () => {
      const saved = await ensureIgSaved();
      const before = saved || profileQ.data;
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      setLiveProgress({
        active: true,
        phase: "queued",
        scraped_posts: 0,
        total_posts: before?.posts_count || 0,
        percent: 0,
        source: "single",
      });
      setScrapingNote(
        before?.username
          ? `Queued — scraping @${before.username}…`
          : "Queued — scraping in background…"
      );
      await api(`/profiles/${profileId}/refresh`, { method: "POST" });
      setScrapingNote(
        before?.username ? `Scraping @${before.username}…` : "Scraping Instagram…"
      );
      const done = await waitForProfileScrape(profileId, {
        since: before?.last_scraped_at,
        prevFollowers: before?.followers,
        prevPosts: before?.posts_count,
        signal: ac.signal,
        onProgress: (prog, profile) => {
          setLiveProgress(prog);
          setScrapingNote(formatScrapeProgress(prog, profile.username));
        },
      });
      return done;
    },
    onSuccess: (done) => {
      setRefreshError("");
      if (done.status === "failed" || done.status === "unavailable") {
        setScrapingNote("");
        setLiveProgress(null);
        setRefreshError(
          humanizeScrapeError(done.last_error) ||
            (done.status === "unavailable"
              ? "This Instagram profile does not exist."
              : "Scrape failed")
        );
      } else if (done.followers > 0 || done.posts_count > 0) {
        setLiveProgress({
          active: false,
          phase: "done",
          scraped_posts: done.scrape_progress?.scraped_posts ?? done.posts_count,
          total_posts: done.scrape_progress?.total_posts ?? done.posts_count,
          percent: 100,
          source: done.scrape_progress?.source,
        });
        const privateNote = done.is_private
          ? " (private account — Instagram hides most posts without login)"
          : "";
        const programmeN = Number((done.insights as { sampled_posts?: number } | undefined)?.sampled_posts ?? 0);
        const storedN = Number((done.insights as { posts_stored?: number } | undefined)?.posts_stored ?? 0);
        const windowNote =
          !done.is_private && done.posts_count > 0 && programmeN === 0 && storedN === 0
            ? ` · 0 programme posts (lifetime ${formatNumber(done.posts_count)} — likely all before 15 Jul 2026)`
            : ` · ${formatNumber(done.posts_count)} posts`;
        setScrapingNote(
          `Done — ${formatNumber(done.followers)} followers${windowNote}${privateNote}`
        );
      } else {
        setLiveProgress(null);
        setRefreshError(
          humanizeScrapeError(done.last_error) ||
            "Scrape finished with no Instagram data. Wait a minute and Refresh again."
        );
        setScrapingNote("");
      }
      void qc.invalidateQueries({ queryKey: ["profile", profileId] });
      void qc.invalidateQueries({ queryKey: ["posts", profileId] });
      void qc.invalidateQueries({ queryKey: ["history", profileId] });
      void qc.invalidateQueries({ queryKey: ["analytics", profileId] });
      void qc.invalidateQueries({ queryKey: ["spark"] });
      void qc.invalidateQueries({ queryKey: ["profiles"] });
      void qc.invalidateQueries({ queryKey: ["scrape-status"] });
    },
    onError: (e: Error) => {
      setScrapingNote("");
      setLiveProgress(null);
      const msg = humanizeScrapeError(e.message) || e.message;
      setRefreshError(msg);
      if (igDirty) setIgError(msg);
    },
  });
  const pause = useMutation({
    mutationFn: () => api(`/profiles/${profileId}/pause`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["profile", profileId] }),
  });
  const del = useMutation({
    mutationFn: () => api(`/profiles/${profileId}`, { method: "DELETE" }),
    onSuccess: () => router.push(adminScrapingListHref()),
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
      {p.status === "unavailable" && (
        <div className="flex items-start gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Profile doesn&apos;t exist on Instagram</div>
            <p className="mt-1 opacity-90">
              {humanizeScrapeError(p.last_error) ||
                `No Instagram account found for @${p.username}. Bulk scrape skipped this handle and continued.`}
            </p>
          </div>
        </div>
      )}
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
      {(liveProgress?.active || p.scrape_progress?.active || (scrapingNote && !refreshError)) && (
        <ScrapeProgressCard
          username={p.username}
          progress={
            liveProgress?.active
              ? liveProgress
              : p.scrape_progress?.active
                ? p.scrape_progress
                : liveProgress || {
                    active: false,
                    phase: "done",
                    percent: 100,
                    scraped_posts: p.posts_count,
                    total_posts: p.posts_count,
                  }
          }
          title={
            liveProgress?.active || p.scrape_progress?.active
              ? `Scraping @${p.username}`
              : scrapingNote || `Scraped @${p.username}`
          }
        />
      )}

      <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <Link href={adminScrapingListHref()} className="text-xs text-zinc-500 hover:text-zinc-300">
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
                  p.status === "failed" && "bg-rose-500/15 text-rose-400",
                  p.status === "unavailable" && "bg-amber-500/15 text-amber-300",
                  p.status !== "failed" &&
                    p.status !== "unavailable" &&
                    "bg-emerald-500/15 text-emerald-400"
                )}
              >
                {p.status === "unavailable" ? "missing" : p.status}
              </span>
            </div>
            {p.bio && <p className="mt-2 max-w-2xl text-sm text-zinc-400 line-clamp-3">{p.bio}</p>}
            <EditableInstagramLink
              value={igDraft}
              onChange={(next) => {
                setIgDraft(next);
                setIgError("");
              }}
              href={igHref}
              editing={igEditing}
              onEditingChange={setIgEditing}
              dirty={igDirty}
              disabled={refresh.isPending}
              saving={saveIgLink.isPending}
              error={igError}
              tone="dark"
              onSave={async () => {
                if (!igDirty) {
                  setIgEditing(false);
                  return;
                }
                await saveIgLink.mutateAsync(igDraft.trim());
              }}
              onCancel={() => {
                setIgDraft(igHref);
                setIgError("");
                setIgEditing(false);
              }}
            />
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
                {p.followers_baseline_date ? (
                  <div
                    className={cn(
                      "text-[11px] tabular",
                      (p.followers_gained ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                    )}
                    title={`Baseline ${formatNumber(p.followers_baseline)} on ${p.followers_baseline_date} (first scrape in programme window)`}
                  >
                    {formatSignedNumber(p.followers_gained ?? 0)} since{" "}
                    {formatBaselineDay(p.followers_baseline_date)}
                    <span className="text-zinc-600"> (first scrape)</span>
                  </div>
                ) : (
                  <div className="text-[11px] text-zinc-600">Scrape once to start tracking gain</div>
                )}
              </div>
              <div>
                <span className="font-semibold tabular">{formatNumber(p.following)}</span>{" "}
                <span className="text-zinc-500">following</span>
              </div>
              <div>
                <span className="font-semibold tabular">
                  {formatNumber(
                    typeof p.programme_posts === "number"
                      ? p.programme_posts
                      : num(insights.sampled_posts)
                  )}
                </span>{" "}
                <span className="text-zinc-500">programme posts</span>
                <span className="ml-1 text-zinc-600">
                  ({formatNumber(p.posts_count)} IG lifetime)
                </span>
              </div>
              <div className={cn("font-semibold tabular", p.growth_pct_today >= 0 ? "text-emerald-400" : "text-rose-400")}>
                {formatPct(p.growth_pct_today)} today
              </div>
            </div>
            {p.website && (
              <a href={p.website} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-sm text-[#ff4d00] hover:underline">
                {p.website}
              </a>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={refresh.isPending || saveIgLink.isPending}
              onClick={() => refresh.mutate()}
              className="inline-flex items-center gap-2 rounded-xl bg-[#ff3b30] px-4 py-2 text-sm font-semibold disabled:opacity-60"
            >
              <RefreshCw size={14} className={refresh.isPending ? "animate-spin" : ""} />
              {refresh.isPending ? "Scraping…" : "Refresh / Scrape"}
            </button>            <button
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
            <p className="mt-2 text-xs text-zinc-500">Today vs previous scrape.</p>
            {p.followers_baseline_date ? (
              <div className="mt-3 border-t border-white/[0.06] pt-3">
                <div
                  className={cn(
                    "text-lg font-semibold tabular",
                    (p.followers_gained ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                  )}
                >
                  {formatSignedNumber(p.followers_gained ?? 0)}
                  <span className="ml-1 text-sm font-normal text-zinc-500">
                    ({formatPct(p.followers_gained_pct ?? 0)})
                  </span>
                </div>
                <p className="mt-1 text-xs text-zinc-500">
                  Since first scrape {formatBaselineDay(p.followers_baseline_date)} (baseline{" "}
                  {formatNumber(p.followers_baseline)})
                </p>
              </div>
            ) : (
              <p className="mt-2 text-xs text-zinc-600">No scrape baseline yet — refresh to start tracking gain.</p>
            )}
          </div>
        </div>
      )}

      {tab === "insights" && (
        <div className="space-y-4">
          <ProgrammeWindowNote
            toDate={
              typeof insights.window_to === "string"
                ? insights.window_to
                : undefined
            }
          />
          <p className="text-xs text-zinc-500">
            Every card below counts <span className="text-zinc-300">only posts dated 15 Jul 2026 → today</span>.
            Posts / 7d and Posts / 30d are rolling windows inside that set — never Instagram lifetime.
            Profile lifetime total (label only):{" "}
            <span className="tabular text-zinc-300">{formatNumber(p.posts_count)}</span> · Highlights:{" "}
            <span className="tabular text-zinc-300">{formatNumber(p.highlight_reel_count || 0)}</span>.
          </p>
          {num(insights.posts_stored) > 0 && num(insights.sampled_posts) === 0 ? (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
              {num(insights.posts_stored)} post(s) are stored for this profile, but none fall inside the programme
              window (15 Jul 2026 → today)
              {num(insights.posts_missing_dates) > 0
                ? ` — ${num(insights.posts_missing_dates)} still have no recoverable date.`
                : " — this account may not have posted since the programme started."}{" "}
              Open the Posts tab to inspect dates, or Refresh again.
            </div>
          ) : null}
          {num(insights.posts_stored) === 0 && num(insights.sampled_posts) === 0 ? (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
              {p.is_private ? (
                <>
                  This account is <span className="font-semibold">private</span>. Instagram hides the post grid
                  without login, so Insights stay at 0. The header &quot;{formatNumber(p.posts_count)} posts&quot; is
                  only the public lifetime count.
                </>
              ) : num(p.posts_count) > 0 ? (
                <>
                  Scrape finished, but <span className="font-semibold">0 posts</span> fall inside the programme
                  window (15 Jul 2026 → today). The header &quot;{formatNumber(p.posts_count)} posts&quot; is
                  Instagram&apos;s lifetime total — those posts are likely all older than 15 Jul 2026 (or dates
                  could not be read). Insights correctly stay at 0 until they post in-window. Try{" "}
                  <span className="font-semibold">Refresh / Scrape</span> once more if you believe they posted
                  after 15 Jul.
                </>
              ) : (
                <>
                  No post rows are saved in the database yet. The header &quot;{formatNumber(p.posts_count)} posts&quot; is
                  Instagram&apos;s lifetime total only — it is not scraped content. Click{" "}
                  <span className="font-semibold">Refresh / Scrape</span> and wait until it finishes; Insights then count
                  only posts from 15 Jul 2026 onward.
                </>
              )}
            </div>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[
              ["Posts in programme", formatNumber(num(insights.sampled_posts))],
              ["Posts / 7d (in window)", formatNumber(num(insights.posts_last_7d))],
              ["Posts / 30d (in window)", formatNumber(num(insights.posts_last_30d))],
              ["Posting / week", `${num(insights.posting_frequency_per_week)}`],
              ["Median likes", formatNumber(num(insights.median_likes))],
              ["Max likes", formatNumber(num(insights.max_likes))],
              ["Min likes", formatNumber(num(insights.min_likes))],
              ["Max reel views", formatNumber(num(insights.max_reel_views || insights.max_views))],
              ["Avg reel views", formatNumber(num(insights.avg_reel_views))],
              ["Total reel views", formatNumber(num(insights.total_reel_views))],
              ["Like / follower %", `${num(insights.like_follower_ratio).toFixed(3)}%`],
              ["Comment / follower %", `${num(insights.comment_follower_ratio).toFixed(3)}%`],
              ["Comments / likes %", `${num(insights.comments_to_likes_ratio).toFixed(2)}%`],
              ["Video share", `${num(insights.video_share_pct)}%`],
              ["Images", formatNumber(num(insights.image_count))],
              ["Reels", formatNumber(num(insights.reel_count))],
              ["Videos", formatNumber(num(insights.video_count))],
              ["Carousels", formatNumber(num(insights.carousel_count))],
              ["Total likes (programme)", formatNumber(num(insights.total_likes_sampled))],
              ["Total comments (programme)", formatNumber(num(insights.total_comments_sampled))],
              ["Posts with views", `${num(insights.posts_with_views)} / ${num(insights.sampled_posts)}`],
              ["Avg caption length", `${num(insights.avg_caption_length)}`],
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
            Insights and SPARK points use programme-window posts only (15 Jul 2026 onward). The header&apos;s
            &quot;IG lifetime&quot; number is Instagram&apos;s profile total and is not used in these cards. Views are
            reel/video play counts — photos/carousels usually have no public view field.
          </p>
        </div>
      )}

      {tab === "posts" && (
        <div className="space-y-3">
          <ProgrammeWindowNote className="!text-xs" />
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
          {!postsQ.data?.length && (
            <p className="text-sm text-zinc-500">No posts in the programme window yet. Click Refresh.</p>
          )}
          </div>
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
