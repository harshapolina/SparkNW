"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { publicApi } from "@/lib/api";
import type { Top10Response } from "@/lib/spark/api-types";
import { cn, formatNumber } from "@/lib/utils";
import { TierBadge } from "@/components/spark/tier-badge";
import { LivePill, ProgressBar, SparkAvatar } from "@/components/spark/ui";
import { BrandLogo } from "@/components/brand-logo";
import { ProgrammeWindowNote } from "@/components/programme-window-note";

export default function PublicTop10Page() {
  const [q, setQ] = useState("");
  const { data, isPending, error } = useQuery({
    queryKey: ["spark", "top-10", "public"],
    queryFn: () => publicApi<Top10Response>("/spark/top-10"),
  });

  const items = useMemo(() => {
    let list = [...(data?.items || [])];
    if (q.trim()) {
      const s = q.toLowerCase();
      list = list.filter(
        (c) =>
          c.name.toLowerCase().includes(s) ||
          c.handle.toLowerCase().includes(s) ||
          c.campus.toLowerCase().includes(s)
      );
    }
    return list;
  }, [data, q]);

  const maxPts = Math.max(...items.map((c) => c.points), 1);

  return (
    <div className="min-h-screen bg-black text-white">
      <div className="mx-auto max-w-5xl space-y-8 px-4 py-8 md:px-8 md:py-12">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <BrandLogo height={28} priority />
            <LivePill />
          </div>
          <div className="flex items-center gap-3 text-xs">
            <Link href="/student-login" className="text-zinc-400 hover:text-white">
              Student login
            </Link>
            <span className="text-zinc-700">·</span>
            <Link href="/admin-login" className="text-zinc-400 hover:text-white">
              Admin login
            </Link>
          </div>
        </div>

        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-xl">
            <h1 className="font-[family-name:var(--font-display)] text-4xl font-semibold tracking-tight md:text-5xl">
              Top the <span className="text-[#ff3b30]">board</span>. Unlock{" "}
              <span className="text-[#ff3b30]">milestones</span>.
            </h1>
            <ProgrammeWindowNote className="mt-3" />
            <p className="mt-3 text-sm leading-relaxed text-zinc-400">
              Points come from posts and follower growth in the programme window. Everyone starts at zero — the board
              only remembers what you posted after the programme started.
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

        <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-500">
          {data?.week_label || "LIVE"} · Top 10 by SPARK points
          {data?.total_creators != null ? ` · ${data.total_creators} creators` : ""}
        </div>

        {isPending && !data && <div className="h-64 animate-pulse rounded-2xl bg-zinc-900" />}
        {error && (
          <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
            {(error as Error).message}
          </div>
        )}

        {!isPending && !error && items.length === 0 && (
          <div className="rounded-2xl border border-white/10 bg-[#121212] p-8 text-center text-sm text-zinc-400">
            Leaderboard is empty. Check back after creators are scraped.
          </div>
        )}

        {items.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-white/[0.06]">
            <div className="grid grid-cols-[72px_minmax(0,1fr)_100px] items-center gap-3 border-b border-white/[0.06] px-4 py-3 text-[10px] font-bold uppercase tracking-[0.14em] text-zinc-500">
              <div>Rank / Creator</div>
              <div />
              <div className="text-right">Points</div>
            </div>
            {items.map((row) => {
              const barColor =
                row.rank <= 3 ? "#ff3b30" : row.tier === "GOLD" ? "#f5c542" : row.tier === "SILVER" ? "#a1a1aa" : "#c47a3a";
              return (
                <div
                  key={row.id}
                  className="grid grid-cols-[72px_minmax(0,1fr)_100px] items-center gap-3 border-b border-white/[0.04] px-4 py-3.5"
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
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="truncate text-sm font-semibold">{row.name}</span>
                          <TierBadge tier={row.tier} />
                        </div>
                        <div className="mt-0.5 text-[11px] text-zinc-500">
                          {row.handle} · {formatNumber(row.followers)} followers · {row.streak_weeks}
                        </div>
                      </div>
                    </div>
                    <ProgressBar className="mt-2" value={row.points} max={maxPts} color={barColor} />
                  </div>
                  <div className="text-right text-sm font-semibold tabular">{formatNumber(row.points)} PTS</div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
