"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Camera, Search, Video } from "lucide-react";
import { api } from "@/lib/api";
import type { CampusUploadsBoard, CampusUploadsBreakdown } from "@/lib/spark/api-types";
import { cn, formatNumber } from "@/lib/utils";

type Platform = "instagram" | "youtube" | "overall";

const HINT: Record<Platform, string> = {
  instagram: "Every Instagram upload in the programme window — posts, reels, and carousels. July counts from 15 Jul.",
  youtube: "Every YouTube upload in the programme window — videos and Shorts. July counts from 15 Jul.",
  overall: "Instagram + YouTube uploads combined, by campus and month. July counts from 15 Jul.",
};

const TITLE: Record<Platform, string> = {
  instagram: "Instagram uploads by campus",
  youtube: "YouTube uploads by campus",
  overall: "All uploads by campus",
};

function heatClass(n: number, max: number): string {
  if (!n || max <= 0) return "text-zinc-600";
  const t = n / max;
  if (t >= 0.7) return "bg-[#ff3b30]/30 text-white font-semibold";
  if (t >= 0.4) return "bg-[#ff3b30]/16 text-zinc-100";
  if (t >= 0.15) return "bg-white/[0.04] text-zinc-200";
  return "text-zinc-400";
}

export function CampusUploadsTable({
  platform,
  title,
}: {
  platform: Platform;
  title?: string;
}) {
  const [q, setQ] = useState("");
  const query = useQuery({
    queryKey: ["spark", "campus-uploads"],
    queryFn: () => api<CampusUploadsBreakdown>("/spark/admin/campus-uploads"),
    staleTime: 60_000,
  });

  const data = query.data;
  const months = data?.months || [];
  const board: CampusUploadsBoard | undefined = data?.[platform];
  const maxCell = Math.max(1, ...(board?.rows || []).flatMap((r) => r.counts), ...(board?.totals || []));
  const thisMonth = months.length ? months[months.length - 1] : null;
  const thisMonthTotal = board?.totals?.[months.length - 1] ?? 0;

  const rows = useMemo(() => {
    const list = board?.rows || [];
    const s = q.trim().toLowerCase();
    if (!s) return list;
    return list.filter((r) => r.campus.toLowerCase().includes(s));
  }, [board, q]);

  const accent =
    platform === "instagram"
      ? "from-[#f58529] via-[#dd2a7b] to-[#8134af]"
      : platform === "youtube"
        ? "from-[#ff3b30] to-[#ff4d00]"
        : "from-[#ff3b30] via-[#ff4d00] to-lime-400";

  return (
    <div className="overflow-hidden rounded-2xl border border-white/[0.08] bg-[#121212]">
      <div className={cn("h-1 w-full bg-gradient-to-r", accent)} />
      <div className="flex flex-col gap-4 border-b border-white/[0.06] px-5 py-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {platform === "youtube" ? (
              <Video size={16} className="text-[#ff3b30]" />
            ) : (
              <Camera size={16} className="text-[#dd2a7b]" />
            )}
            <h2 className="text-sm font-semibold tracking-tight">{title || TITLE[platform]}</h2>
          </div>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-zinc-500">{HINT[platform]}</p>
        </div>
        <label className="flex w-full max-w-xs items-center gap-2 rounded-xl border border-white/10 bg-black/40 px-3 py-2">
          <Search size={14} className="text-zinc-500" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter campus…"
            className="w-full bg-transparent text-sm outline-none placeholder:text-zinc-600"
          />
        </label>
      </div>

      {board && months.length > 0 ? (
        <div className="grid gap-px border-b border-white/[0.06] bg-white/[0.04] sm:grid-cols-3">
          <div className="bg-[#121212] px-5 py-3">
            <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">Total uploads</div>
            <div className="mt-1 text-2xl font-semibold tabular">{formatNumber(board.grand_total)}</div>
          </div>
          <div className="bg-[#121212] px-5 py-3">
            <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">Campuses</div>
            <div className="mt-1 text-2xl font-semibold tabular">{formatNumber(board.rows.length)}</div>
          </div>
          <div className="bg-[#121212] px-5 py-3">
            <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">
              {thisMonth?.label || "This month"}
            </div>
            <div className="mt-1 text-2xl font-semibold tabular text-[#ff3b30]">{formatNumber(thisMonthTotal)}</div>
          </div>
        </div>
      ) : null}

      {query.isPending && !data ? (
        <div className="h-48 animate-pulse bg-zinc-900/60" />
      ) : query.error ? (
        <p className="px-5 py-8 text-sm text-rose-300">{(query.error as Error).message}</p>
      ) : !months.length || !board?.rows.length ? (
        <p className="px-5 py-8 text-sm text-zinc-500">No uploads in the programme window yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="sticky top-0 z-10 bg-[#1a1a1a]">
              <tr className="border-b border-white/10 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-400">
                <th className="sticky left-0 z-20 bg-[#1a1a1a] px-5 py-3">Campus</th>
                {months.map((m) => (
                  <th key={m.id} className="min-w-[108px] px-3 py-3 text-right">
                    {m.label}
                  </th>
                ))}
                <th className="min-w-[88px] px-5 py-3 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr
                  key={row.campus}
                  className={cn(
                    "border-b border-white/[0.04]",
                    idx % 2 === 0 ? "bg-black/20" : "bg-transparent"
                  )}
                >
                  <td className="sticky left-0 max-w-[260px] truncate bg-[#121212] px-5 py-3 font-medium text-zinc-100">
                    {row.campus}
                  </td>
                  {row.counts.map((n, i) => (
                    <td key={months[i]?.id || i} className="px-2 py-2 text-right">
                      <span
                        className={cn(
                          "inline-flex min-w-[3.25rem] justify-end rounded-lg px-2 py-1 tabular",
                          heatClass(n, maxCell)
                        )}
                      >
                        {formatNumber(n)}
                      </span>
                    </td>
                  ))}
                  <td className="px-5 py-3 text-right">
                    <div className="flex flex-col items-end gap-1">
                      <span className="font-semibold tabular">{formatNumber(row.total)}</span>
                      <span className="h-1 w-16 overflow-hidden rounded-full bg-white/10">
                        <span
                          className="block h-full rounded-full bg-gradient-to-r from-[#f58529] to-[#dd2a7b]"
                          style={{
                            width: `${Math.min(100, board.grand_total ? (row.total / board.grand_total) * 100 : 0)}%`,
                          }}
                        />
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-white/10 bg-[#161616]">
                <td className="sticky left-0 bg-[#161616] px-5 py-3 font-semibold">All campuses</td>
                {board.totals.map((n, i) => (
                  <td key={months[i]?.id || i} className="px-3 py-3 text-right font-semibold tabular">
                    {formatNumber(n)}
                  </td>
                ))}
                <td className="px-5 py-3 text-right text-base font-semibold tabular text-[#ff3b30]">
                  {formatNumber(board.grand_total)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
