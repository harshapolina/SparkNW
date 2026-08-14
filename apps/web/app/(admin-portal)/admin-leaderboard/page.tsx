"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Download, Search } from "lucide-react";
import { api } from "@/lib/api";
import type { AdminOverviewResponse, LeaderboardResponse, SparkCreatorRow } from "@/lib/spark/api-types";
import type { LeaderboardSort } from "@/lib/spark/types";
import { cn, formatNumber } from "@/lib/utils";
import { TierBadge } from "@/components/spark/tier-badge";
import { Movement, SparkAvatar } from "@/components/spark/ui";
import { ProgrammeWindowNote } from "@/components/programme-window-note";
import { NumberedPagination } from "@/components/numbered-pagination";
import { defaultCohortRange, utcTodayYmd } from "@/lib/spark/cohort";

const sorts: { id: LeaderboardSort; label: string }[] = [
  { id: "overall", label: "OVERALL" },
  { id: "points", label: "POINTS" },
  { id: "followers", label: "FOLLOWERS" },
  { id: "views", label: "VIEWS" },
  { id: "engagement", label: "ENGAGEMENT" },
];

const PAGE_SIZE = 20;

function buildLeaderboardUrl(sort: LeaderboardSort, fromDate: string, toDate: string) {
  const params = new URLSearchParams({ sort });
  params.set("from_date", fromDate);
  params.set("to_date", toDate);
  return `/spark/leaderboard?${params.toString()}`;
}

export default function AdminLeaderboardPage() {
  // Fixed programme window: 15 Jul 2026 → today (no calendar picker).
  const range = defaultCohortRange(utcTodayYmd());
  const [sort, setSort] = useState<LeaderboardSort>("overall");
  const [campus, setCampus] = useState<string>("all");
  const [tier, setTier] = useState<string>("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  const boardQ = useQuery({
    queryKey: ["spark", "leaderboard", sort, range.from, range.to],
    queryFn: () => api<LeaderboardResponse>(buildLeaderboardUrl(sort, range.from, range.to)),
  });
  const adminQ = useQuery({
    queryKey: ["spark", "admin"],
    queryFn: () => api<AdminOverviewResponse>("/spark/admin"),
  });

  const ranked = useMemo(() => {
    let list: SparkCreatorRow[] = [...(boardQ.data?.items || [])];
    if (campus !== "all") list = list.filter((c) => c.campus === campus);
    if (tier !== "all") list = list.filter((c) => c.tier === tier);
    if (q.trim()) {
      const s = q.toLowerCase();
      list = list.filter(
        (c) =>
          c.name.toLowerCase().includes(s) ||
          c.handle.toLowerCase().includes(s) ||
          c.campus.toLowerCase().includes(s) ||
          (c.team || "").toLowerCase().includes(s)
      );
    }
    return list.map((c, i) => ({ ...c, rank: i + 1 }));
  }, [boardQ.data, campus, tier, q]);

  const totalPages = Math.max(1, Math.ceil(ranked.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageRows = ranked.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const admin = adminQ.data;
  const campuses = boardQ.data?.campuses || [];
  const appliedTo = boardQ.data?.to_date || range.to;

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const exportCsv = () => {
    const header = ["Rank", "Name", "Handle", "Campus", "Team", "Tier", "Points", "Followers", "Views", "Engagement", "Trend"];
    const lines = ranked.map((c) =>
      [c.rank, c.name, c.handle, c.campus, c.team || "", c.tier, c.points, c.followers, c.views, c.engagement, c.rank_delta].join(",")
    );
    const blob = new Blob([[header.join(","), ...lines].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `spark-leaderboard-${range.from}_to_${appliedTo}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (boardQ.isPending && !boardQ.data) return <div className="h-64 animate-pulse rounded-2xl bg-zinc-900" />;
  if (boardQ.error) {
    return (
      <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
        {(boardQ.error as Error).message}
      </div>
    );
  }

  const kpiCards = [
    { label: "Total Creators", value: formatNumber(admin?.total_participants ?? ranked.length), sub: "Across campuses" },
    {
      label: "Total Points Distributed",
      value: formatNumber(admin?.total_points_distributed ?? 0),
      sub:
        admin?.points_wow_pct != null
          ? `${admin.points_wow_pct > 0 ? "+" : ""}${admin.points_wow_pct.toFixed(1)}% WoW`
          : "SPARK point system",
      subClass: (admin?.points_wow_pct ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400",
    },
    { label: "Total Followers (All)", value: formatNumber(admin?.total_followers ?? 0), sub: "Live scrapes" },
    { label: "Total Views (All)", value: formatNumber(admin?.total_views ?? 0), sub: "Post views sum" },
    { label: "Total Engagement (All)", value: formatNumber(admin?.total_engagement ?? 0), sub: "Likes + comments" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Leaderboard</h1>
          <ProgrammeWindowNote className="mt-1" toDate={appliedTo} />
          <p className="mt-1 text-sm text-zinc-500">
            Sort pills reorder by real scraped metrics. OVERALL uses SPARK points from programme-start through today.
            Scraping ignores earlier posts.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link href="/admin-scraping" className="rounded-xl border border-white/10 bg-[#121212] px-3 py-2 text-xs text-zinc-300 hover:border-[#ff4d00]/40">
            Manage scraping
          </Link>
          <button
            type="button"
            onClick={exportCsv}
            className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-[#121212] px-3 py-2 text-xs font-medium hover:border-[#ff4d00]/40"
          >
            <Download size={14} /> Export
          </button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {kpiCards.map((k) => (
          <div key={k.label} className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4">
            <div className="text-[11px] uppercase tracking-[0.1em] text-zinc-500">{k.label}</div>
            <div className="mt-2 text-2xl font-semibold tabular">{k.value}</div>
            <div className={cn("mt-1 text-[11px]", "subClass" in k && k.subClass ? k.subClass : "text-zinc-500")}>
              {k.sub}
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4 md:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] pb-4">
          <ProgrammeWindowNote variant="compact" toDate={appliedTo} />
          <p className="text-[11px] text-zinc-500">Live window — end date is today and updates daily.</p>
        </div>

        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-nowrap items-center gap-1.5 overflow-x-auto pb-0.5">
            {sorts.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => {
                  setSort(s.id);
                  setPage(1);
                }}
                className={cn(
                  "shrink-0 rounded-full px-3.5 py-1.5 text-[11px] font-bold tracking-[0.08em] transition",
                  sort === s.id ? "bg-white text-black" : "bg-zinc-900 text-zinc-400 hover:text-zinc-200"
                )}
              >
                {s.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <label className="flex min-w-0 w-full flex-1 items-center gap-2 rounded-xl border border-white/10 bg-black/40 px-3 py-2 sm:min-w-[200px]">
              <Search size={14} className="text-zinc-500" />
              <input
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setPage(1);
                }}
                placeholder="Search by name, team or campus..."
                className="w-full bg-transparent text-sm outline-none placeholder:text-zinc-600"
              />
            </label>
            <select
              value={campus}
              onChange={(e) => {
                setCampus(e.target.value);
                setPage(1);
              }}
              className="w-full rounded-xl border border-white/10 bg-[#121212] px-3 py-2 text-sm text-zinc-100 [color-scheme:dark] sm:w-auto"
            >
              <option value="all" className="bg-[#121212] text-zinc-100">
                All campuses
              </option>
              {campuses.map((c) => (
                <option key={c} value={c} className="bg-[#121212] text-zinc-100">
                  {c}
                </option>
              ))}
            </select>
            <select
              value={tier}
              onChange={(e) => {
                setTier(e.target.value);
                setPage(1);
              }}
              className="w-full rounded-xl border border-white/10 bg-[#121212] px-3 py-2 text-sm text-zinc-100 [color-scheme:dark] sm:w-auto"
            >
              <option value="all" className="bg-[#121212] text-zinc-100">
                All tiers
              </option>
              <option value="GOLD" className="bg-[#121212] text-zinc-100">
                Gold
              </option>
              <option value="SILVER" className="bg-[#121212] text-zinc-100">
                Silver
              </option>
              <option value="BRONZE" className="bg-[#121212] text-zinc-100">
                Bronze
              </option>
            </select>
          </div>
        </div>

        <div className="mt-4 space-y-3 lg:hidden">
          {pageRows.map((row) => (
            <Link
              key={row.id}
              href={`/admin-scraping/${row.id}`}
              className="block rounded-2xl border border-white/[0.06] bg-black/30 p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2.5">
                  <span
                    className={cn(
                      "w-8 shrink-0 text-lg font-semibold tabular",
                      row.rank === 1 && "text-[#cd7f32]",
                      row.rank === 2 && "text-zinc-300",
                      row.rank === 3 && "text-[#f5c542]",
                      row.rank > 3 && "text-zinc-500"
                    )}
                  >
                    {row.rank}
                  </span>
                  <SparkAvatar initials={row.initials} size="sm" accent={row.rank <= 3} />
                  <div className="min-w-0">
                    <div className="truncate font-medium text-zinc-100">
                      {row.name}
                      {row.team ? ` · ${row.team}` : ""}
                    </div>
                    <div className="truncate text-[11px] text-zinc-500">
                      {row.handle} · {row.campus}
                    </div>
                  </div>
                </div>
                <TierBadge tier={row.tier} />
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-zinc-500 sm:grid-cols-3">
                <div>
                  <div className="uppercase tracking-wide">Points</div>
                  <div className="mt-0.5 text-sm tabular text-[#ff4d00]">{formatNumber(row.points)}</div>
                </div>
                <div>
                  <div className="uppercase tracking-wide">Followers</div>
                  <div className="mt-0.5 text-sm tabular text-zinc-200">{formatNumber(row.followers)}</div>
                </div>
                <div>
                  <div className="uppercase tracking-wide">Engagement</div>
                  <div className="mt-0.5 text-sm tabular text-zinc-200">{Number(row.engagement || 0).toFixed(2)}%</div>
                </div>
              </div>
              <div className="mt-2 flex items-center justify-between text-[11px] text-zinc-500">
                <span>
                  YT {row.youtube_connected ? `${formatNumber(row.youtube_subscribers ?? 0)} subs` : "—"}
                </span>
                <Movement delta={row.rank_delta} />
              </div>
            </Link>
          ))}
          {!pageRows.length && (
            <div className="rounded-2xl border border-white/[0.06] px-3 py-10 text-center text-zinc-500">
              No creators match these filters.
            </div>
          )}
        </div>

        <div className="mt-4 hidden overflow-x-auto lg:block">
          <table className="w-full min-w-[1100px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-[10px] uppercase tracking-[0.12em] text-zinc-500">
                <th className="px-3 py-3 font-semibold">Rank</th>
                <th className="px-3 py-3 font-semibold">Creator / Team</th>
                <th className="px-3 py-3 font-semibold">Campus</th>
                <th className="px-3 py-3 font-semibold">Tier</th>
                <th
                  className={cn(
                    "px-3 py-3 font-semibold",
                    (sort === "overall" || sort === "points") && "text-[#ff4d00]"
                  )}
                >
                  SPARK Points{(sort === "overall" || sort === "points") ? " ↓" : ""}
                </th>
                <th className={cn("px-3 py-3 font-semibold", sort === "followers" && "text-[#ff4d00]")}>
                  Followers{sort === "followers" ? " ↓" : ""}
                </th>
                <th className={cn("px-3 py-3 font-semibold", sort === "views" && "text-[#ff4d00]")}>
                  Views{sort === "views" ? " ↓" : ""}
                </th>
                <th className={cn("px-3 py-3 font-semibold", sort === "engagement" && "text-[#ff4d00]")}>
                  Engagement{sort === "engagement" ? " ↓" : ""}
                </th>
                <th className="px-3 py-3 font-semibold" title="Display only — not in SPARK points yet">
                  YT Subs
                </th>
                <th className="px-3 py-3 font-semibold" title="Display only — not in SPARK points yet">
                  YT Views
                </th>
                <th className="px-3 py-3 font-semibold">Trend</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row) => (
                <tr key={row.id} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                  <td
                    className={cn(
                      "px-3 py-3 font-semibold tabular",
                      row.rank === 1 && "text-[#cd7f32]",
                      row.rank === 2 && "text-zinc-300",
                      row.rank === 3 && "text-[#f5c542]",
                      row.rank > 3 && "text-zinc-500"
                    )}
                  >
                    {row.rank}
                  </td>
                  <td className="px-3 py-3">
                    <Link href={`/admin-scraping/${row.id}`} className="flex items-center gap-2.5 hover:opacity-90">
                      <SparkAvatar initials={row.initials} size="sm" accent={row.rank <= 3} />
                      <div>
                        <div className="font-medium text-zinc-100">
                          {row.name}
                          {row.team ? ` · ${row.team}` : ""}
                        </div>
                        <div className="text-[11px] text-zinc-500">{row.handle}</div>
                      </div>
                    </Link>
                  </td>
                  <td className="px-3 py-3 text-zinc-400">{row.campus}</td>
                  <td className="px-3 py-3">
                    <TierBadge tier={row.tier} />
                  </td>
                  <td
                    className={cn(
                      "px-3 py-3 tabular",
                      sort === "overall" || sort === "points" ? "text-[#ff4d00]" : "text-zinc-200"
                    )}
                  >
                    {formatNumber(row.points)}
                  </td>
                  <td
                    className={cn(
                      "px-3 py-3 tabular",
                      sort === "followers" ? "font-semibold text-[#ff4d00]" : "text-zinc-200"
                    )}
                  >
                    {formatNumber(row.followers)}
                  </td>
                  <td
                    className={cn(
                      "px-3 py-3 tabular",
                      sort === "views" ? "font-semibold text-[#ff4d00]" : "text-zinc-200"
                    )}
                  >
                    {formatNumber(row.views)}
                  </td>
                  <td
                    className={cn(
                      "px-3 py-3 tabular",
                      sort === "engagement" ? "font-semibold text-[#ff4d00]" : "text-zinc-200"
                    )}
                  >
                    {Number(row.engagement || 0).toFixed(2)}%
                  </td>
                  <td className="px-3 py-3 tabular text-zinc-400">
                    {row.youtube_connected ? formatNumber(row.youtube_subscribers ?? 0) : "—"}
                  </td>
                  <td className="px-3 py-3 tabular text-zinc-400">
                    {row.youtube_connected ? formatNumber(row.youtube_views ?? 0) : "—"}
                  </td>
                  <td className="px-3 py-3">
                    <Movement delta={row.rank_delta} />
                  </td>
                </tr>
              ))}
              {!pageRows.length && (
                <tr>
                  <td colSpan={11} className="px-3 py-10 text-center text-zinc-500">
                    No creators match these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <p className="mt-3 text-[11px] text-zinc-500">
          <span className="text-zinc-300">OVERALL / POINTS</span> = SPARK score from scraped posts since 15 Jul 2026.{" "}
          <span className="text-zinc-300">FOLLOWERS / VIEWS / ENGAGEMENT</span> = cohort metrics from that date onward.{" "}
          <span className="text-zinc-300">YT Subs / YT Views</span> = display only (not in SPARK points yet).
          Orange column is the active sort.
        </p>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-zinc-500">
          <span>
            {ranked.length} creators
            {(campus !== "all" || tier !== "all" || q.trim()) && " (filtered)"}
            {ranked.length > 0 ? ` · page ${safePage} of ${totalPages}` : ""}
          </span>
          <NumberedPagination
            page={safePage}
            pageSize={PAGE_SIZE}
            total={ranked.length}
            onPageChange={setPage}
          />
        </div>
      </div>
    </div>
  );
}
