"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, Download, Plus, RefreshCw, Search } from "lucide-react";
import { api, type Profile } from "@/lib/api";
import { cn, formatBaselineDay, formatNumber, formatPct, formatSignedNumber } from "@/lib/utils";
import { SparkAvatar } from "@/components/spark/ui";
import { formatScrapeProgress, waitForProfileScrape } from "@/lib/wait-for-scrape";
import { progressPercent, type ScrapeStatusResponse } from "@/lib/scrape-progress";
import {
  ScrapeActivityBanner,
  ScrapeProgressCard,
  ScrapeRowProgress,
} from "@/components/scrape-progress";
import { NumberedPagination } from "@/components/numbered-pagination";
import {
  readAdminScrapingListState,
  writeAdminScrapingListState,
} from "@/lib/admin-scraping-list-state";

export type ScrapingBoardView = "overall" | "instagram" | "youtube";

type ListResponse = { items: Profile[]; total: number; page: number; page_size: number };

const STATUS_FILTERS = [
  { id: "", label: "All" },
  { id: "active", label: "Active" },
  { id: "private", label: "Private" },
  { id: "failed", label: "Failed" },
  { id: "paused", label: "Paused" },
  { id: "unavailable", label: "Unavailable" },
] as const;

const VIEW_COPY: Record<
  ScrapingBoardView,
  { title: string; subtitle: string }
> = {
  overall: {
    title: "Scraping / All platforms",
    subtitle:
      "Instagram scrapes and YouTube syncs in one place. Use the sidebar to focus on a single platform.",
  },
  instagram: {
    title: "Instagram scraping",
    subtitle:
      "Add creators, queue Instagram scrapes, and manage the cohort table. YouTube lives on its own page.",
  },
  youtube: {
    title: "YouTube sync",
    subtitle:
      "Creator board, live queue, and daily YouTube updates. Instagram scraping is on its own page.",
  },
};

function AdminScrapingBoardInner({ view }: { view: ScrapingBoardView }) {
  const qc = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Restore page from session when URL has no page (e.g. bare /admin-scraping link).
  useEffect(() => {
    if (view === "youtube") return;
    if (searchParams.has("page") || searchParams.has("q") || searchParams.has("status")) return;
    const stored = readAdminScrapingListState();
    if (!stored || (stored.page <= 1 && !stored.q && !stored.status)) return;
    const params = new URLSearchParams();
    if (stored.q.trim()) params.set("q", stored.q.trim());
    if (stored.status) params.set("status", stored.status);
    if (stored.page > 1) params.set("page", String(stored.page));
    const qs = params.toString();
    if (qs) router.replace(`${pathname}?${qs}`, { scroll: false });
  }, [searchParams, pathname, router, view]);

  const page = Math.max(1, Number.parseInt(searchParams.get("page") || "1", 10) || 1);
  const statusFilter = searchParams.get("status") || "";
  const q = searchParams.get("q") || "";
  const [qInput, setQInput] = useState(q);

  useEffect(() => {
    setQInput(q);
  }, [q]);

  useEffect(() => {
    writeAdminScrapingListState({ page, q, status: statusFilter });
  }, [page, q, statusFilter]);

  const replaceListParams = useCallback(
    (patch: { page?: number; q?: string; status?: string }) => {
      const nextQ = patch.q !== undefined ? patch.q : q;
      const nextStatus = patch.status !== undefined ? patch.status : statusFilter;
      const nextPage = patch.page !== undefined ? patch.page : page;
      const params = new URLSearchParams();
      if (nextQ.trim()) params.set("q", nextQ.trim());
      if (nextStatus) params.set("status", nextStatus);
      if (nextPage > 1) params.set("page", String(nextPage));
      const qs = params.toString();
      writeAdminScrapingListState({ page: nextPage, q: nextQ, status: nextStatus });
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, q, statusFilter, page, router]
  );

  const [ig, setIg] = useState("");
  const [studentId, setStudentId] = useState("");
  const [fullName, setFullName] = useState("");
  const [university, setUniversity] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState("");

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (q) params.set("q", q);
    if (statusFilter) params.set("status", statusFilter);
    return params.toString();
  }, [q, page, statusFilter]);

  // Debounce search typing into the URL (keeps page when returning from a profile).
  useEffect(() => {
    const t = window.setTimeout(() => {
      if (qInput === q) return;
      replaceListParams({ q: qInput, page: 1 });
    }, 300);
    return () => window.clearTimeout(t);
  }, [qInput, q, replaceListParams]);

  const scrapeStatusQ = useQuery({
    queryKey: ["scrape-status"],
    queryFn: () => api<ScrapeStatusResponse>("/profiles/scrape-status"),
    refetchInterval: (query) => {
      const n = query.state.data?.active_count || 0;
      return n > 0 ? 2500 : 8000;
    },
  });

  const dailyScrapeQ = useQuery({
    queryKey: ["settings", "daily-scrape"],
    queryFn: () => api<{ enabled: boolean }>("/settings/daily-scrape"),
  });

  const dailyScrapeToggle = useMutation({
    mutationFn: (enabled: boolean) =>
      api<{ enabled: boolean }>("/settings/daily-scrape", {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: (data) => {
      qc.setQueryData(["settings", "daily-scrape"], data);
      setBulkNote(
        data.enabled
          ? "Auto-scrape ON — unfinished bulk resumes now; mornings run as scheduled."
          : "Auto-scrape OFF — mornings + bulk auto queue paused. Manual Refresh still works."
      );
    },
    onError: (e: Error) => setError(e.message),
  });

  const dailyYoutubeQ = useQuery({
    queryKey: ["settings", "daily-youtube-sync"],
    queryFn: () => api<{ enabled: boolean }>("/settings/daily-youtube-sync"),
  });

  const dailyYoutubeToggle = useMutation({
    mutationFn: (enabled: boolean) =>
      api<{ enabled: boolean }>("/settings/daily-youtube-sync", {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: (data) => {
      qc.setQueryData(["settings", "daily-youtube-sync"], data);
      setBulkNote(
        data.enabled
          ? "YouTube sync ON — connected channels queued now. Watch the YouTube queue below."
          : "Daily YouTube sync is OFF — Instagram scrape is unchanged."
      );
      void qc.invalidateQueries({ queryKey: ["youtube", "sync-status"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  type YtSyncRow = {
    job_id?: string;
    profile_id: string;
    username: string;
    full_name?: string | null;
    student_id?: string | null;
    university?: string | null;
    channel_id?: string | null;
    channel_name?: string | null;
    handle?: string | null;
    thumbnail_url?: string | null;
    status?: string;
    sync_status?: string;
    job_status?: string | null;
    error_message?: string | null;
    last_error?: string | null;
    last_synced_at?: string | null;
    created_at?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
    subscriber_count?: number | null;
    hidden_subscriber_count?: boolean;
    view_count?: number;
    video_count?: number | null;
    connected?: boolean;
    youtube_ref?: string | null;
  };

  type YtSyncStatus = {
    running: YtSyncRow | null;
    queue: YtSyncRow[];
    active_count: number;
    history: YtSyncRow[];
    connected: YtSyncRow[];
    connected_total: number;
    board?: YtSyncRow[];
    board_total?: number;
  };

  const YT_STATUS_FILTERS = [
    { id: "", label: "All" },
    { id: "connected", label: "Connected" },
    { id: "syncing", label: "Syncing" },
    { id: "success", label: "Success" },
    { id: "failed", label: "Failed" },
    { id: "not_connected", label: "Not connected" },
    { id: "quota_exceeded", label: "Quota" },
  ] as const;

  const [ytQInput, setYtQInput] = useState("");
  const [ytStatusFilter, setYtStatusFilter] = useState("");
  const [ytSelected, setYtSelected] = useState<string[]>([]);

  const youtubeSyncQ = useQuery({
    queryKey: ["youtube", "sync-status"],
    queryFn: () => api<YtSyncStatus>("/youtube/sync-status"),
    refetchInterval: (q) => ((q.state.data?.active_count || 0) > 0 ? 3000 : 15000),
  });

  const youtubeBoardRows = useMemo(() => {
    const rows = youtubeSyncQ.data?.board || youtubeSyncQ.data?.connected || [];
    const qLower = ytQInput.trim().toLowerCase();
    return rows.filter((row) => {
      const isConnected = row.connected !== false && row.sync_status !== "not_connected";
      const displayStatus = row.job_status || row.sync_status || "";
      if (ytStatusFilter === "connected" && !isConnected) return false;
      if (ytStatusFilter === "not_connected" && isConnected) return false;
      if (ytStatusFilter === "syncing") {
        if (!["pending", "running", "retrying"].includes(String(row.job_status || ""))) return false;
      } else if (
        ytStatusFilter === "success" ||
        ytStatusFilter === "failed" ||
        ytStatusFilter === "quota_exceeded"
      ) {
        if (displayStatus !== ytStatusFilter && row.sync_status !== ytStatusFilter) return false;
      } else if (ytStatusFilter && ytStatusFilter !== "connected" && ytStatusFilter !== "not_connected") {
        if (displayStatus !== ytStatusFilter && row.sync_status !== ytStatusFilter) return false;
      }
      if (!qLower) return true;
      const hay = [
        row.full_name,
        row.username,
        row.student_id,
        row.university,
        row.channel_name,
        row.handle,
        row.channel_id,
        row.youtube_ref,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(qLower);
    });
  }, [youtubeSyncQ.data, ytQInput, ytStatusFilter]);

  const ytAllIds = useMemo(() => youtubeBoardRows.map((r) => r.profile_id), [youtubeBoardRows]);

  const youtubeSyncAll = useMutation({
    mutationFn: () =>
      api<{ enqueued: number; skipped_pending: number; connected_total: number; dispatched: number }>(
        "/youtube/sync-all",
        { method: "POST" }
      ),
    onSuccess: (data) => {
      setBulkNote(
        `YouTube sync queued ${data.enqueued} channel(s)` +
          (data.skipped_pending ? ` (${data.skipped_pending} already in queue)` : "") +
          ` · ${data.connected_total} connected`
      );
      void qc.invalidateQueries({ queryKey: ["youtube", "sync-status"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const youtubeSyncSelected = useMutation({
    mutationFn: async () => {
      const ids = ytSelected.filter(Boolean);
      let ok = 0;
      let fail = 0;
      for (const pid of ids) {
        try {
          await api(`/youtube/profiles/${pid}/sync`, {
            method: "POST",
            body: JSON.stringify({ max_videos: 0, fetch_videos: true }),
          });
          ok += 1;
        } catch {
          fail += 1;
        }
      }
      return { ok, fail };
    },
    onSuccess: (r) => {
      setBulkNote(`YouTube sync finished for ${r.ok} selected` + (r.fail ? ` · ${r.fail} failed` : ""));
      setYtSelected([]);
      void qc.invalidateQueries({ queryKey: ["youtube", "sync-status"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const { data, isLoading } = useQuery({
    queryKey: ["profiles", q, page, statusFilter],
    queryFn: () => api<ListResponse>(`/profiles?${queryString}`),
    refetchInterval: () => ((scrapeStatusQ.data?.active_count || 0) > 0 ? 3000 : false),
  });

  const [bulkNote, setBulkNote] = useState("");
  const [addProgress, setAddProgress] = useState<{
    percent: number;
    label: string;
    username?: string;
    progress?: Profile["scrape_progress"];
  } | null>(null);

  const add = useMutation({
    mutationFn: async () => {
      setAddProgress({
        percent: 0,
        label: "Creating profile…",
        username: ig.trim().replace(/^@/, ""),
      });
      const created = await api<Profile>("/profiles", {
        method: "POST",
        body: JSON.stringify({
          url: ig.trim(),
          student: {
            student_id: studentId.trim(),
            full_name: fullName.trim() || undefined,
            university: university.trim() || undefined,
            instagram_username: ig.trim().replace(/^@/, ""),
          },
        }),
      });
      setAddProgress({
        percent: 5,
        label: `Queued — scraping @${created.username}…`,
        username: created.username,
        progress: created.scrape_progress,
      });
      return waitForProfileScrape(created.id, {
        since: created.last_scraped_at,
        prevFollowers: created.followers,
        prevPosts: created.posts_count,
        onProgress: (prog, profile) => {
          setAddProgress({
            percent: progressPercent(prog),
            label: formatScrapeProgress(prog, profile.username),
            username: profile.username,
            progress: prog || undefined,
          });
        },
      });
    },
    onSuccess: (p) => {
      setIg("");
      setStudentId("");
      setFullName("");
      setUniversity("");
      setError("");
      setAddProgress(null);
      setBulkNote(
        p.followers > 0 || p.posts_count > 0 || (p.programme_posts ?? 0) > 0
          ? `Scraped @${p.username} — ${formatNumber(p.followers)} followers · ${formatNumber(p.programme_posts ?? 0)} programme posts (${formatNumber(p.posts_count)} IG)`
          : `Added @${p.username} — scrape still running or no public posts yet`
      );
      qc.invalidateQueries({ queryKey: ["profiles"] });
      qc.invalidateQueries({ queryKey: ["scrape-status"] });
      qc.invalidateQueries({ queryKey: ["spark"] });
    },
    onError: (e: Error) => {
      setAddProgress(null);
      setError(e.message);
    },
  });

  const bulk = useMutation({
    mutationFn: async (action: "refresh" | "delete" | "pause" | "resume" | "export") => {
      if (action === "export") {
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/profiles/bulk/export`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${localStorage.getItem("is_access_token")}`,
            },
            body: JSON.stringify({ ids: selected }),
          }
        );
        if (!res.ok) throw new Error("Export failed");
        const blob = await res.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "spark-profiles-export.csv";
        a.click();
        return { action, queued: 0 };
      }
      const res = await api<unknown>(`/profiles/bulk/${action}`, {
        method: "POST",
        body: JSON.stringify({ ids: selected }),
      });
      const queued = Array.isArray(res) ? res.length : selected.length;
      return { action, queued };
    },
    onSuccess: (r) => {
      const count = selected.length;
      setSelected([]);
      setError("");
      if (r?.action === "refresh") {
        setBulkNote(
          `Queued ${r.queued} profile(s). Watch the live progress bar below — one account at a time.`
        );
      } else if (r?.action === "export") {
        setBulkNote("Export downloaded.");
      } else if (r?.action) {
        setBulkNote(`${r.action} applied to ${count} profile(s).`);
      } else {
        setBulkNote("");
      }
      qc.invalidateQueries({ queryKey: ["profiles"] });
      qc.invalidateQueries({ queryKey: ["scrape-status"] });
      qc.invalidateQueries({ queryKey: ["spark"] });
    },
    onError: (e: Error) => {
      setBulkNote("");
      setError(e.message);
    },
  });

  const allIds = useMemo(() => data?.items.map((p) => p.id) || [], [data]);

  function onAdd(e: FormEvent) {
    e.preventDefault();
    if (!studentId.trim()) {
      setError("NIAT / Student ID is required so the student can log in later.");
      return;
    }
    if (!ig.trim()) {
      setError("Instagram handle or URL is required.");
      return;
    }
    add.mutate();
  }

  const showInstagram = view === "overall" || view === "instagram";
  const showYoutube = view === "overall" || view === "youtube";

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#ff3b30]">
            Scraping
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">{VIEW_COPY[view].title}</h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-500">{VIEW_COPY[view].subtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {showInstagram ? (
          <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-[#121212] px-4 py-2.5">
            <div className="min-w-0">
              <div className="text-xs font-semibold text-zinc-200">Auto-scrape</div>
              <div className="text-[11px] text-zinc-500">
                {dailyScrapeQ.data?.enabled === false
                  ? "Off — no morning/bulk auto (stays until you turn on)"
                  : "On — mornings + unfinished bulk scrape without .env flips"}
              </div>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={dailyScrapeQ.data?.enabled !== false}
              disabled={dailyScrapeQ.isLoading || dailyScrapeToggle.isPending}
              onClick={() =>
                dailyScrapeToggle.mutate(!(dailyScrapeQ.data?.enabled !== false))
              }
              className={cn(
                "relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50",
                dailyScrapeQ.data?.enabled === false ? "bg-zinc-700" : "bg-[#ff3b30]"
              )}
            >
              <span
                className={cn(
                  "absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform",
                  dailyScrapeQ.data?.enabled === false ? "translate-x-0" : "translate-x-5"
                )}
              />
            </button>
          </div>
          ) : null}
          {showYoutube ? (
          <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-[#121212] px-4 py-2.5">
            <div className="min-w-0">
              <div className="text-xs font-semibold text-zinc-200">Daily YouTube sync</div>
              <div className="text-[11px] text-zinc-500">
                {dailyYoutubeQ.data?.enabled !== false
                  ? "On — bulk import auto-connects + daily 08:00 IST updates"
                  : "Off — no morning YouTube sync"}
              </div>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={dailyYoutubeQ.data?.enabled !== false}
              disabled={dailyYoutubeQ.isLoading || dailyYoutubeToggle.isPending}
              onClick={() =>
                dailyYoutubeToggle.mutate(!(dailyYoutubeQ.data?.enabled !== false))
              }
              className={cn(
                "relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50",
                dailyYoutubeQ.data?.enabled === false ? "bg-zinc-700" : "bg-[#ff3b30]"
              )}
            >
              <span
                className={cn(
                  "absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform",
                  dailyYoutubeQ.data?.enabled === false ? "translate-x-0" : "translate-x-5"
                )}
              />
            </button>
          </div>
          ) : null}
          <Link
            href="/admin-import"
            className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-[#121212] px-4 py-2 text-sm text-zinc-300 hover:border-[#ff3b30]/40 hover:text-white"
          >
            Bulk roster import →
          </Link>
        </div>
      </div>

      {showInstagram ? <ScrapeActivityBanner status={scrapeStatusQ.data} /> : null}

      {showYoutube ? (
      <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-zinc-100">YouTube sync queue</div>
            <p className="mt-0.5 text-xs text-zinc-500">
              Live jobs + past syncs. Bulk import auto-connects YouTube from sheet links; daily 08:00 IST refreshes updates.
            </p>
          </div>
          <button
            type="button"
            disabled={youtubeSyncAll.isPending}
            onClick={() => youtubeSyncAll.mutate()}
            className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-xs font-medium text-zinc-200 hover:border-[#ff3b30]/40 disabled:opacity-50"
          >
            <RefreshCw size={14} className={youtubeSyncAll.isPending ? "animate-spin" : undefined} />
            {youtubeSyncAll.isPending ? "Queuing…" : "Sync all connected"}
          </button>
        </div>

        {(youtubeSyncQ.data?.active_count || 0) > 0 ? (
          <div className="mt-4 space-y-2 rounded-xl border border-violet-500/25 bg-violet-500/10 px-4 py-3 text-violet-100">
            <div className="text-sm font-semibold">
              Syncing now
              {youtubeSyncQ.data?.running
                ? ` — @${youtubeSyncQ.data.running.username}`
                : ` (${youtubeSyncQ.data?.active_count} in queue)`}
              <span className="ml-2 font-normal text-violet-200/70">
                · {youtubeSyncQ.data?.active_count} job(s)
              </span>
            </div>
            <ul className="max-h-48 space-y-1.5 overflow-y-auto overscroll-contain pr-1 text-xs text-violet-100/90 sm:max-h-56">
              {(youtubeSyncQ.data?.queue || []).map((row) => (
                <li key={row.job_id || row.profile_id} className="flex flex-wrap items-center gap-2">
                  <Link
                    href={`/admin-scraping/${row.profile_id}`}
                    className="font-medium text-white hover:underline"
                  >
                    @{row.username}
                  </Link>
                  <span className="rounded-full bg-black/30 px-2 py-0.5 uppercase tracking-wide text-[10px]">
                    {row.status}
                  </span>
                  {row.channel_name ? (
                    <span className="text-violet-200/70">{row.channel_name}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="mt-3 text-xs text-zinc-500">
            No YouTube jobs in queue
            {youtubeSyncQ.data?.connected_total
              ? ` · ${youtubeSyncQ.data.connected_total} channel(s) connected`
              : " · connect channels on a profile first"}
            .
          </p>
        )}

        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.1em] text-zinc-500">
              Past YouTube syncs
            </div>
            {(youtubeSyncQ.data?.history || []).length ? (
              <ul className="max-h-64 space-y-2 overflow-auto text-xs">
                {youtubeSyncQ.data!.history.map((row) => (
                  <li
                    key={row.job_id || `${row.profile_id}-${row.finished_at}`}
                    className="rounded-xl border border-white/[0.06] bg-black/30 px-3 py-2"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <Link
                        href={`/admin-scraping/${row.profile_id}`}
                        className="font-medium text-zinc-200 hover:text-[#ff4d00]"
                      >
                        @{row.username}
                      </Link>
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide",
                          row.status === "success"
                            ? "bg-emerald-500/15 text-emerald-300"
                            : "bg-rose-500/15 text-rose-300"
                        )}
                      >
                        {row.status}
                      </span>
                    </div>
                    <div className="mt-1 text-zinc-500">
                      {row.finished_at
                        ? new Date(row.finished_at).toLocaleString()
                        : row.created_at
                          ? new Date(row.created_at).toLocaleString()
                          : "—"}
                      {row.channel_name ? ` · ${row.channel_name}` : ""}
                    </div>
                    {row.error_message ? (
                      <p className="mt-1 text-rose-300/90 line-clamp-2">{row.error_message}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-zinc-500">No past YouTube sync jobs yet.</p>
            )}
          </div>

          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.1em] text-zinc-500">
              Connected channels
            </div>
            <p className="text-xs text-zinc-500">
              {youtubeSyncQ.data?.connected_total || 0} connected · see board below
            </p>
          </div>
        </div>
      </div>
      ) : null}

      {showYoutube ? (
      <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <label className="relative w-full max-w-sm shrink">
              <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500" />
              <input
                value={ytQInput}
                onChange={(e) => setYtQInput(e.target.value)}
                placeholder="Search name, student ID, campus, channel…"
                className="w-full rounded-full border border-white/10 bg-black py-2.5 pl-10 pr-4 text-sm outline-none focus:border-[#ff3b30]"
              />
            </label>
            <div className="flex max-w-full shrink-0 flex-nowrap items-center gap-1 overflow-x-auto pb-0.5">
              {YT_STATUS_FILTERS.map((f) => (
                <button
                  key={f.id || "all"}
                  type="button"
                  onClick={() => setYtStatusFilter(f.id)}
                  className={cn(
                    "shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-medium",
                    ytStatusFilter === f.id ? "bg-white text-black" : "bg-zinc-900 text-zinc-400"
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={!ytSelected.length || youtubeSyncSelected.isPending}
              onClick={() => youtubeSyncSelected.mutate()}
              className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-black px-3 py-2 text-xs font-medium text-zinc-300 disabled:opacity-40 hover:border-white/20"
            >
              <RefreshCw size={14} className={youtubeSyncSelected.isPending ? "animate-spin" : undefined} />
              Sync selected
            </button>
            <button
              type="button"
              disabled={youtubeSyncAll.isPending}
              onClick={() => youtubeSyncAll.mutate()}
              className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-black px-3 py-2 text-xs font-medium text-zinc-300 disabled:opacity-40 hover:border-white/20"
            >
              <RefreshCw size={14} />
              Sync all connected
            </button>
          </div>
        </div>

        <div className="mt-5 overflow-x-auto">
          {!youtubeBoardRows.length ? (
            <div className="rounded-xl border border-dashed border-white/10 px-6 py-12 text-center text-sm text-zinc-500">
              No YouTube rows yet. Import a roster with YouTube links, or connect channels on creator pages.
            </div>
          ) : (
            <div className="max-h-[70vh] overflow-y-auto overscroll-contain">
              <table className="min-w-[1100px] w-full text-left text-sm">
                <thead className="sticky top-0 z-10 bg-[#121212]">
                  <tr className="border-b border-white/[0.06] text-[10px] uppercase tracking-[0.12em] text-zinc-500">
                    <th className="px-2 py-3">
                      <input
                        type="checkbox"
                        checked={!!ytAllIds.length && ytSelected.length === ytAllIds.length}
                        onChange={(e) => setYtSelected(e.target.checked ? ytAllIds : [])}
                      />
                    </th>
                    <th className="px-2 py-3">Creator</th>
                    <th className="px-2 py-3">Student ID</th>
                    <th className="px-2 py-3">Campus</th>
                    <th className="px-2 py-3">Subscribers</th>
                    <th className="px-2 py-3">Views</th>
                    <th className="px-2 py-3">Videos</th>
                    <th className="px-2 py-3">Sync status</th>
                    <th className="px-2 py-3">Last synced</th>
                  </tr>
                </thead>
                <tbody>
                  {youtubeBoardRows.map((row) => {
                    const live = row.job_status || "";
                    const status = live || row.sync_status || "—";
                    return (
                      <tr key={row.profile_id} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                        <td className="px-2 py-3">
                          <input
                            type="checkbox"
                            checked={ytSelected.includes(row.profile_id)}
                            onChange={(e) =>
                              setYtSelected((prev) =>
                                e.target.checked
                                  ? [...prev, row.profile_id]
                                  : prev.filter((id) => id !== row.profile_id)
                              )
                            }
                          />
                        </td>
                        <td className="px-2 py-3">
                          <Link
                            href={`/admin-scraping/${row.profile_id}`}
                            className="flex items-center gap-3 hover:opacity-90"
                          >
                            <SparkAvatar
                              initials={(row.full_name || row.username || "?")
                                .slice(0, 2)
                                .toUpperCase()}
                              size="sm"
                            />
                            <div>
                              <div className="font-medium">{row.full_name || row.username}</div>
                              <div className="text-[11px] text-zinc-500">@{row.username}</div>
                              <div className="text-[11px] text-zinc-500">
                                {row.channel_name || row.handle || row.youtube_ref || "No channel yet"}
                              </div>
                              {row.last_error ? (
                                <div className="mt-0.5 flex items-center gap-1 text-[11px] text-rose-400">
                                  <AlertCircle size={11} /> Sync issue
                                </div>
                              ) : null}
                            </div>
                          </Link>
                        </td>
                        <td className="px-2 py-3 tabular text-zinc-300">{row.student_id || "—"}</td>
                        <td className="px-2 py-3 text-zinc-400">{row.university || "—"}</td>
                        <td className="px-2 py-3 tabular">
                          {row.hidden_subscriber_count
                            ? "Hidden"
                            : row.subscriber_count != null
                              ? formatNumber(row.subscriber_count)
                              : "—"}
                        </td>
                        <td className="px-2 py-3 tabular">
                          {row.connected ? formatNumber(row.view_count || 0) : "—"}
                        </td>
                        <td className="px-2 py-3 tabular">
                          {row.connected ? formatNumber(row.video_count || 0) : "—"}
                        </td>
                        <td className="px-2 py-3">
                          <span
                            className={cn(
                              "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase",
                              ["pending", "running", "retrying"].includes(live) &&
                                "bg-sky-500/15 text-sky-300",
                              status === "success" && "bg-lime-500/15 text-lime-400",
                              (status === "failed" || status === "unavailable") &&
                                "bg-rose-500/15 text-rose-400",
                              status === "quota_exceeded" && "bg-amber-500/15 text-amber-300",
                              status === "not_connected" && "bg-zinc-700/80 text-zinc-300"
                            )}
                          >
                            {status.replace(/_/g, " ")}
                          </span>
                        </td>
                        <td className="px-2 py-3 text-[11px] whitespace-nowrap text-zinc-500">
                          {row.last_synced_at
                            ? new Date(row.last_synced_at).toLocaleString()
                            : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <div className="mt-4 text-xs text-zinc-500">
          {youtubeBoardRows.length} shown
          {youtubeSyncQ.data?.board_total
            ? ` · ${youtubeSyncQ.data.board_total} total`
            : ""}{" "}
          · {ytSelected.length} selected
        </div>
        {bulkNote && showYoutube ? (
          <p className="mt-3 text-sm text-emerald-400/90">{bulkNote}</p>
        ) : null}
        {error && showYoutube && !showInstagram ? (
          <p className="mt-2 text-sm text-rose-400">{error}</p>
        ) : null}
      </div>
      ) : null}

      {showInstagram ? (
      <>
      <form onSubmit={onAdd} className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
        <div className="text-sm font-semibold">Add & scrape one creator</div>
        <p className="mt-1 text-xs text-zinc-500">Creates the student profile, then scrapes Instagram immediately.</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <label className="space-y-1.5 text-xs">
            <span className="uppercase tracking-[0.1em] text-zinc-500">Student ID (required)</span>
            <input
              value={studentId}
              onChange={(e) => setStudentId(e.target.value)}
              placeholder="NIAT24A001"
              className="w-full rounded-xl border border-white/10 bg-black px-3 py-2.5 text-sm outline-none focus:border-[#ff3b30]"
            />
          </label>
          <label className="space-y-1.5 text-xs">
            <span className="uppercase tracking-[0.1em] text-zinc-500">Instagram (required)</span>
            <input
              value={ig}
              onChange={(e) => setIg(e.target.value)}
              placeholder="@handle or profile URL"
              className="w-full rounded-xl border border-white/10 bg-black px-3 py-2.5 text-sm outline-none focus:border-[#ff3b30]"
            />
          </label>
          <label className="space-y-1.5 text-xs">
            <span className="uppercase tracking-[0.1em] text-zinc-500">Full name</span>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Optional"
              className="w-full rounded-xl border border-white/10 bg-black px-3 py-2.5 text-sm outline-none focus:border-[#ff3b30]"
            />
          </label>
          <label className="space-y-1.5 text-xs">
            <span className="uppercase tracking-[0.1em] text-zinc-500">University / Campus</span>
            <input
              value={university}
              onChange={(e) => setUniversity(e.target.value)}
              placeholder="NIAT, CDU…"
              className="w-full rounded-xl border border-white/10 bg-black px-3 py-2.5 text-sm outline-none focus:border-[#ff3b30]"
            />
          </label>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={add.isPending}
            className="inline-flex items-center gap-2 rounded-xl bg-[#ff3b30] px-4 py-2.5 text-sm font-semibold disabled:opacity-60"
          >
            <Plus size={16} />
            {add.isPending ? "Scraping…" : "Add & scrape"}
          </button>
          {error && <p className="text-sm text-rose-400">{error}</p>}
        </div>
        {addProgress ? (
          <div className="mt-4">
            <ScrapeProgressCard
              username={addProgress.username}
              progress={addProgress.progress}
              title={
                addProgress.username
                  ? `Scraping @${addProgress.username}`
                  : "Scraping in progress"
              }
            />
          </div>
        ) : null}
      </form>

      <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <label className="relative w-full max-w-sm shrink">
              <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500" />
              <input
                value={qInput}
                onChange={(e) => setQInput(e.target.value)}
                placeholder="Search name, student ID, campus, @handle…"
                className="w-full rounded-full border border-white/10 bg-black py-2.5 pl-10 pr-4 text-sm outline-none focus:border-[#ff3b30]"
              />
            </label>
            <div className="flex max-w-full shrink-0 flex-nowrap items-center gap-1 overflow-x-auto pb-0.5" title="Active = public tracked accounts. Private = Instagram-private accounts (rechecked each morning).">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.id || "all"}
                  type="button"
                  onClick={() => replaceListParams({ status: f.id, page: 1 })}
                  title={
                    f.id === "active"
                      ? "Public accounts currently tracked (excludes private)"
                      : f.id === "private"
                        ? "All Instagram-private accounts"
                        : undefined
                  }
                  className={cn(
                    "shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-medium",
                    statusFilter === f.id ? "bg-white text-black" : "bg-zinc-900 text-zinc-400"
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {(
              [
                ["refresh", "Refresh / Scrape", RefreshCw],
                ["pause", "Pause", null],
                ["resume", "Resume", null],
                ["export", "Export CSV", Download],
              ] as const
            ).map(([action, label, Icon]) => (
              <button
                key={action}
                type="button"
                disabled={!selected.length || bulk.isPending}
                onClick={() => bulk.mutate(action)}
                className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-black px-3 py-2 text-xs font-medium text-zinc-300 disabled:opacity-40 hover:border-white/20"
              >
                {Icon ? <Icon size={14} /> : null}
                {label}
              </button>
            ))}
            <button
              type="button"
              disabled={!selected.length || bulk.isPending}
              onClick={() => bulk.mutate("delete")}
              className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs font-medium text-rose-300 disabled:opacity-40"
            >
              Delete
            </button>
          </div>
        </div>
        {bulkNote ? <p className="mt-3 text-sm text-emerald-400/90">{bulkNote}</p> : null}
        {error && !add.isPending ? <p className="mt-2 text-sm text-rose-400">{error}</p> : null}

        <div className="mt-5 overflow-x-auto">
          {isLoading ? (
            <div className="h-40 animate-pulse rounded-xl bg-zinc-900" />
          ) : !data?.items.length ? (
            <div className="rounded-xl border border-dashed border-white/10 px-6 py-12 text-center text-sm text-zinc-500">
              No creators yet. Add one above or{" "}
              <Link href="/admin-import" className="text-[#ff3b30] hover:underline">
                import a roster sheet
              </Link>
              .
            </div>
          ) : (
            <table className="min-w-[1100px] w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/[0.06] text-[10px] uppercase tracking-[0.12em] text-zinc-500">
                  <th className="px-2 py-3">
                    <input
                      type="checkbox"
                      checked={!!allIds.length && selected.length === allIds.length}
                      onChange={(e) => setSelected(e.target.checked ? allIds : [])}
                    />
                  </th>
                  <th className="px-2 py-3">Creator</th>
                  <th className="px-2 py-3">Student ID</th>
                  <th className="px-2 py-3">Campus</th>
                  <th className="px-2 py-3">Followers</th>
                  <th className="px-2 py-3" title="Posts dated from 15 Jul 2026 (programme window)">
                    Prog. posts
                  </th>
                  <th className="px-2 py-3">Scrape progress</th>
                  <th className="px-2 py-3">Growth</th>
                  <th className="px-2 py-3">Status</th>
                  <th className="px-2 py-3">Scraped</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((p) => (
                  <tr key={p.id} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                    <td className="px-2 py-3">
                      <input
                        type="checkbox"
                        checked={selected.includes(p.id)}
                        onChange={(e) =>
                          setSelected((prev) =>
                            e.target.checked ? [...prev, p.id] : prev.filter((id) => id !== p.id)
                          )
                        }
                      />
                    </td>
                    <td className="px-2 py-3">
                      <Link href={`/admin-scraping/${p.id}`} className="flex items-center gap-3 hover:opacity-90">
                        <SparkAvatar
                          initials={(p.student?.full_name || p.full_name || p.username || "?")
                            .slice(0, 2)
                            .toUpperCase()}
                          size="sm"
                        />
                        <div>
                          <div className="flex flex-wrap items-center gap-1.5 font-medium">
                            <span>{p.student?.full_name || p.full_name || p.username}</span>
                            {p.is_private ? (
                              <span className="rounded-full bg-violet-500/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-violet-300">
                                Private
                              </span>
                            ) : null}
                          </div>
                          <div className="text-[11px] text-zinc-500">@{p.username}</div>
                          {p.status === "failed" && (
                            <div className="mt-0.5 flex items-center gap-1 text-[11px] text-rose-400">
                              <AlertCircle size={11} /> Scrape failed
                            </div>
                          )}
                          {p.status === "unavailable" && (
                            <div className="mt-0.5 flex items-center gap-1 text-[11px] text-amber-400">
                              <AlertCircle size={11} /> Profile doesn&apos;t exist
                            </div>
                          )}
                        </div>
                      </Link>
                    </td>
                    <td className="px-2 py-3 tabular text-zinc-300">{p.student?.student_id || "—"}</td>
                    <td className="px-2 py-3 text-zinc-400">{p.student?.university || "—"}</td>
                    <td className="px-2 py-3 tabular">
                      <div>{formatNumber(p.followers)}</div>
                      {p.followers_baseline_date ? (
                        <div
                          className={cn(
                            "text-[10px]",
                            (p.followers_gained ?? 0) >= 0 ? "text-lime-400" : "text-rose-400"
                          )}
                          title={`Since first scrape ${p.followers_baseline_date} (baseline ${formatNumber(p.followers_baseline)})`}
                        >
                          {formatSignedNumber(p.followers_gained ?? 0)} since{" "}
                          {formatBaselineDay(p.followers_baseline_date)}
                        </div>
                      ) : null}
                    </td>
                    <td className="px-2 py-3 tabular">
                      <div className="font-medium text-zinc-100">
                        {formatNumber(typeof p.programme_posts === "number" ? p.programme_posts : 0)}
                      </div>
                      <div className="text-[10px] text-zinc-600" title="Instagram lifetime post count">
                        {formatNumber(p.posts_count)} IG total
                      </div>
                    </td>
                    <td className="px-2 py-3">
                      {p.scrape_progress?.active ? (
                        <ScrapeRowProgress username={p.username} progress={p.scrape_progress} />
                      ) : (
                        <span className="text-[11px] text-zinc-600">—</span>
                      )}
                    </td>
                    <td
                      className={cn(
                        "px-2 py-3 tabular",
                        p.growth_pct_today >= 0 ? "text-lime-400" : "text-rose-400"
                      )}
                    >
                      {formatPct(p.growth_pct_today)}
                    </td>
                    <td className="px-2 py-3">
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase",
                          p.scrape_progress?.active && "bg-sky-500/15 text-sky-300",
                          !p.scrape_progress?.active &&
                            p.is_private &&
                            "bg-violet-500/15 text-violet-300",
                          !p.scrape_progress?.active &&
                            !p.is_private &&
                            p.status === "active" &&
                            "bg-lime-500/15 text-lime-400",
                          !p.scrape_progress?.active &&
                            !p.is_private &&
                            p.status === "failed" &&
                            "bg-rose-500/15 text-rose-400",
                          !p.scrape_progress?.active &&
                            !p.is_private &&
                            p.status === "unavailable" &&
                            "bg-amber-500/15 text-amber-400",
                          !p.scrape_progress?.active &&
                            !p.is_private &&
                            p.status === "paused" &&
                            "bg-amber-500/15 text-amber-400"
                        )}
                      >
                        {p.scrape_progress?.active
                          ? "scraping"
                          : p.is_private
                            ? "private"
                            : p.status === "unavailable"
                              ? "missing"
                              : p.status}
                      </span>
                    </td>
                    <td className="px-2 py-3 text-[11px] text-zinc-500 whitespace-nowrap">
                      {p.last_scraped_at ? new Date(p.last_scraped_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-zinc-500">
          <span>
            {data?.total || 0} creators · {selected.length} selected
            {data && data.page_size
              ? ` · page ${page} of ${Math.max(1, Math.ceil(data.total / data.page_size))}`
              : ""}
          </span>
          <NumberedPagination
            page={page}
            pageSize={data?.page_size || 20}
            total={data?.total || 0}
            onPageChange={(next) => replaceListParams({ page: next })}
          />
        </div>
      </div>
      </>
      ) : null}
    </div>
  );
}

export function AdminScrapingBoard({ view }: { view: ScrapingBoardView }) {
  return (
    <Suspense fallback={<div className="h-64 animate-pulse rounded-2xl bg-zinc-900" />}>
      <AdminScrapingBoardInner view={view} />
    </Suspense>
  );
}
