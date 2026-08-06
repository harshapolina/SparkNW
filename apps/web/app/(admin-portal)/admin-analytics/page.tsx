"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, BadgeCheck } from "lucide-react";
import { api } from "@/lib/api";
import type { AdminOverviewResponse } from "@/lib/spark/api-types";
import { cn, formatNumber, formatPct } from "@/lib/utils";

export default function AdminAnalyticsPage() {
  const { data, isPending, error } = useQuery({
    queryKey: ["spark", "admin"],
    queryFn: () => api<AdminOverviewResponse>("/spark/admin"),
  });

  const items = data?.portfolio || data?.recent_updates || [];

  if (isPending && !data) return <div className="h-48 animate-pulse rounded-2xl bg-zinc-900" />;
  if (error) {
    return (
      <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
        {(error as Error).message}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href="/admin-dashboard" className="text-xs text-zinc-500 hover:text-zinc-300">
          ← Dashboard
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Portfolio analytics</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Every tracked creator with followers, engagement, and avg likes — same as the old Analytics page.
        </p>
      </div>

      {!items.length && (
        <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-8 text-center text-sm text-zinc-500">
          Nothing to analyze yet. Import and scrape creators first.
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {items.map((p) => (
          <Link
            key={p.id}
            href={`/admin-scraping/${p.id}`}
            className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5 transition hover:border-[#ff3b30]/40"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 truncate font-semibold">
                  @{p.username}
                  {p.is_verified && <BadgeCheck size={14} className="text-sky-400" />}
                </div>
                <div className="truncate text-xs text-zinc-500">{p.full_name || p.campus || "—"}</div>
              </div>
              <ArrowUpRight size={15} className="shrink-0 text-zinc-600" />
            </div>
            <div className="mt-5 grid grid-cols-3 gap-3 border-t border-white/[0.04] pt-4">
              <div>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500">Followers</div>
                <div className="mt-1 text-sm font-semibold tabular">{formatNumber(p.followers)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500">Engage</div>
                <div className="mt-1 text-sm font-semibold tabular">{p.engagement_rate.toFixed(2)}%</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500">Avg likes</div>
                <div className="mt-1 text-sm font-semibold tabular">{formatNumber(p.avg_likes)}</div>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-zinc-500">
              <span>Views {formatNumber(p.avg_views)}</span>
              <span>·</span>
              <span>Posts {formatNumber(p.posts_count)}</span>
              <span>·</span>
              <span className={cn(p.growth_pct_today >= 0 ? "text-emerald-400" : "text-rose-400")}>
                {formatPct(p.growth_pct_today)}
              </span>
              <span>·</span>
              <span className="capitalize">{p.status}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
