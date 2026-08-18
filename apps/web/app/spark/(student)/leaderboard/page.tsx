"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api } from "@/lib/api";
import type { LeaderboardResponse, SparkCreatorRow } from "@/lib/spark/api-types";
import { cn, formatNumber } from "@/lib/utils";
import { TierBadge } from "@/components/spark/tier-badge";
import { LivePill, Movement, ProgressBar, SparkAvatar } from "@/components/spark/ui";

export default function StudentLeaderboardPage() {
  const [scope, setScope] = useState<"all" | "campus">("all");
  const [q, setQ] = useState("");

  const { data, isPending, error } = useQuery({
    queryKey: ["spark", "leaderboard", "overall"],
    queryFn: () => api<LeaderboardResponse>("/spark/leaderboard?sort=overall"),
  });

  const you = useMemo(() => {
    const items = data?.items || [];
    return items[0] || null;
  }, [data]);

  const campusFilter = scope === "campus" && you ? you.campus : null;

  const ranked = useMemo(() => {
    let list = [...(data?.items || [])];
    if (campusFilter) list = list.filter((c) => c.campus === campusFilter);
    if (q.trim()) {
      const s = q.toLowerCase();
      list = list.filter(
        (c) =>
          c.name.toLowerCase().includes(s) ||
          c.handle.toLowerCase().includes(s) ||
          c.campus.toLowerCase().includes(s)
      );
    }
    if (campusFilter && !q.trim()) {
      return list.map((c, i) => ({ ...c, rank: i + 1 }));
    }
    return list;
  }, [data, campusFilter, q]);

  const top10 = ranked.slice(0, 10);
  const maxPts = Math.max(...ranked.map((c) => c.points), 1);

  const metricValue = (c: SparkCreatorRow) => `${formatNumber(c.points)} PTS`;
  const barValue = (c: SparkCreatorRow) => c.points;
  const barMax = maxPts;

  if (isPending && !data) return <div className="h-64 animate-pulse rounded-2xl bg-zinc-900" />;
  if (error) {
    return (
      <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
        {(error as Error).message}
      </div>
    );
  }

  if (!ranked.length) {
    return (
      <div className="rounded-2xl border border-white/10 bg-[#121212] p-8 text-center">
        <h1 className="text-2xl font-semibold">Leaderboard is empty</h1>
        <p className="mt-2 text-sm text-zinc-400">Import or add profiles, then Refresh to scrape live metrics.</p>
        <Link href="/profiles" className="mt-4 inline-flex text-[#ff3b30] hover:underline">
          Add profiles →
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <LivePill />
          <span className="text-xs text-zinc-500">SPARK / Rankings</span>
        </div>
        <div className="text-right text-[11px] uppercase tracking-[0.12em] text-zinc-500">
          <div>LIVE COHORT</div>
          <div className="mt-0.5 normal-case tracking-normal">Powered by InstaScope scrapes</div>
        </div>
      </div>

      <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-xl">
          <h1 className="font-[family-name:var(--font-display)] text-4xl font-semibold tracking-tight md:text-5xl">
            Top the board.
            <br />
            <span className="text-[#ff3b30]">Unlock milestones.</span>
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-zinc-400">
            Overall rank uses the SPARK point system (consistency + content performance + audience growth) from real
            scraped posts. Use My campus to see only your campus creators.
          </p>
        </div>
        <label className="flex w-full max-w-sm items-center gap-2 rounded-full border border-white/10 bg-[#121212] px-4 py-2.5">
          <Search size={15} className="text-zinc-500" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search creator by name or handle..."
            className="w-full bg-transparent text-sm outline-none placeholder:text-zinc-600"
          />
        </label>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-1 rounded-full bg-zinc-900 p-1 text-[11px] font-semibold">
          <button
            type="button"
            onClick={() => setScope("all")}
            className={cn("rounded-full px-3 py-1.5", scope === "all" ? "bg-white text-black" : "text-zinc-400")}
          >
            ALL CREATORS
          </button>
          <button
            type="button"
            onClick={() => setScope("campus")}
            className={cn("rounded-full px-3 py-1.5", scope === "campus" ? "bg-white text-black" : "text-zinc-400")}
          >
            MY CAMPUS
          </button>
        </div>
      </div>

      {scope === "campus" && you && (
        <div className="rounded-xl border border-white/10 bg-[#121212] px-4 py-2 text-xs text-zinc-400">
          Showing campus <span className="text-white">{you.campus}</span>
          {(data?.campuses || []).length > 1 ? ` · ${(data?.campuses || []).join(" · ")}` : ""}
        </div>
      )}

      <div className="overflow-x-auto rounded-2xl border border-white/[0.06]">
        <div className="min-w-[720px]">
          <div className="grid grid-cols-[72px_minmax(0,1fr)_76px_72px_96px] items-center gap-3 border-b border-white/[0.06] px-4 py-3 text-[10px] font-bold uppercase tracking-[0.14em] text-zinc-500">
            <div>Rank</div>
            <div>Creator</div>
            <div className="text-center">Tier</div>
            <div className="text-right">Move</div>
            <div className="text-right">Score</div>
          </div>

          {top10.map((row) => {
            const barColor =
              row.rank === 1 ? "#ff3b30" : row.tier === "GOLD" ? "#f5c542" : row.tier === "SILVER" ? "#a1a1aa" : "#c47a3a";
            return (
              <Link
                key={row.id}
                href={`/profiles/${row.id}`}
                className="grid grid-cols-[72px_minmax(0,1fr)_76px_72px_96px] items-center gap-3 border-b border-white/[0.04] px-4 py-3.5 transition hover:bg-white/[0.02]"
              >
                <div
                  className={cn(
                    "text-2xl font-semibold tabular",
                    row.rank === 1 && "text-[#ff3b30]",
                    row.rank === 2 && "text-[#ff7a45]",
                    row.rank === 3 && "text-[#f5c542]",
                    row.rank > 3 && "text-zinc-500"
                  )}
                >
                  {String(row.rank).padStart(2, "0")}
                </div>

                <div className="min-w-0">
                  <div className="flex items-center gap-2.5">
                    <SparkAvatar initials={row.initials} size="sm" accent={row.rank === 1} />
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold">{row.name}</div>
                      <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-zinc-500">
                        <span className="truncate">
                          {row.handle} · {formatNumber(row.followers)} followers · {row.streak_weeks}
                        </span>
                        <span
                          className={cn(
                            "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em]",
                            scope === "campus" && you?.campus === row.campus
                              ? "bg-white text-black"
                              : "bg-zinc-800 text-zinc-300"
                          )}
                        >
                          {scope === "campus" && you?.campus === row.campus ? "My campus" : row.campus}
                        </span>
                      </div>
                    </div>
                  </div>
                  <ProgressBar className="mt-2" value={barValue(row)} max={barMax} color={barColor} />
                </div>

                <div className="flex justify-center">
                  <TierBadge tier={row.tier} />
                </div>

                <div className="text-right">
                  <Movement delta={row.rank_delta} />
                </div>

                <div className="text-right text-sm font-semibold tabular">{metricValue(row)}</div>
              </Link>
            );
          })}

          {you && (
            <div className="border border-[#ff3b30]/50 bg-[#ff3b30]/5 px-4 py-4">
              <div className="grid grid-cols-[72px_minmax(0,1fr)_76px_72px_96px] items-center gap-3">
                <div className="text-2xl font-semibold tabular text-[#ff3b30]">#{you.rank}</div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2.5">
                    <SparkAvatar initials={you.initials} accent size="sm" />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 truncate text-sm font-semibold">
                        <span className="truncate">{you.name}</span>
                        <span className="shrink-0 rounded bg-[#ff3b30] px-1.5 py-0.5 text-[10px] font-bold">TOP</span>
                      </div>
                      <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-zinc-400">
                        <span className="truncate">
                          {you.handle} · {formatNumber(you.points)} SPARK pts · {you.streak_weeks}
                        </span>
                        <span
                          className={cn(
                            "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em]",
                            scope === "campus" ? "bg-white text-black" : "bg-zinc-800 text-zinc-300"
                          )}
                        >
                          {scope === "campus" ? "My campus" : you.campus}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="flex justify-center">
                  <TierBadge tier={you.tier} />
                </div>
                <div className="text-right">
                  <Movement delta={you.rank_delta} />
                </div>
                <div className="text-right">
                  <div className="text-sm font-semibold tabular">{formatNumber(you.points)} PTS</div>
                  <Link href="/spark/dashboard" className="text-[11px] text-[#ff3b30] hover:underline">
                    Dashboard →
                  </Link>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-zinc-600">
        <span>
          SHOWING {Math.min(10, ranked.length)} OF {ranked.length} CREATORS
        </span>
        <Link href="/spark/admin/leaderboard" className="hover:text-zinc-300">
          Admin board →
        </Link>
      </div>
    </div>
  );
}
