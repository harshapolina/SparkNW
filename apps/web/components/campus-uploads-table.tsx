"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Camera, Download, RotateCcw, Search, Trash2, Video } from "lucide-react";
import { api } from "@/lib/api";
import type { CampusUploadsBoard, CampusUploadsBreakdown } from "@/lib/spark/api-types";
import { cn, formatNumber } from "@/lib/utils";

type Platform = "instagram" | "youtube" | "overall";

type EditRow = {
  id: string;
  campus: string;
  counts: number[];
};

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

function csvEscape(value: string): string {
  if (/[",\n\r]/.test(value)) return `"${value.replace(/"/g, '""')}"`;
  return value;
}

function parseCount(raw: string): number {
  const n = Number(String(raw).replace(/[^\d.-]/g, ""));
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.round(n);
}

function boardToEditRows(board: CampusUploadsBoard | undefined): EditRow[] {
  return (board?.rows || []).map((r, i) => ({
    id: `${r.campus || "campus"}-${i}`,
    campus: r.campus,
    counts: [...r.counts],
  }));
}

function summarize(rows: EditRow[], monthCount: number) {
  const totals = Array.from({ length: monthCount }, () => 0);
  let grand = 0;
  const withTotals = rows.map((r) => {
    const total = r.counts.reduce((a, b) => a + (Number(b) || 0), 0);
    r.counts.forEach((n, i) => {
      if (i < totals.length) totals[i] += Number(n) || 0;
    });
    grand += total;
    return { ...r, total };
  });
  return { rows: withTotals, totals, grand_total: grand };
}

export function CampusUploadsTable({
  platform,
  title,
}: {
  platform: Platform;
  title?: string;
}) {
  const [q, setQ] = useState("");
  const [editRows, setEditRows] = useState<EditRow[]>([]);
  const [dirty, setDirty] = useState(false);

  const query = useQuery({
    queryKey: ["spark", "campus-uploads"],
    queryFn: () => api<CampusUploadsBreakdown>("/spark/admin/campus-uploads"),
    staleTime: 60_000,
  });

  const data = query.data;
  const months = data?.months || [];
  const board: CampusUploadsBoard | undefined = data?.[platform];

  useEffect(() => {
    if (!board) return;
    setEditRows(boardToEditRows(board));
    setDirty(false);
  }, [board, platform]);

  const summary = useMemo(() => summarize(editRows, months.length), [editRows, months.length]);
  const maxCell = Math.max(1, ...summary.rows.flatMap((r) => r.counts), ...summary.totals);
  const thisMonth = months.length ? months[months.length - 1] : null;
  const thisMonthTotal = summary.totals[months.length - 1] ?? 0;

  const rows = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return summary.rows;
    return summary.rows.filter((r) => r.campus.toLowerCase().includes(s));
  }, [summary.rows, q]);

  const accent =
    platform === "instagram"
      ? "from-[#f58529] via-[#dd2a7b] to-[#8134af]"
      : platform === "youtube"
        ? "from-[#ff3b30] to-[#ff4d00]"
        : "from-[#ff3b30] via-[#ff4d00] to-lime-400";

  function updateCampus(id: string, campus: string) {
    setDirty(true);
    setEditRows((prev) => prev.map((r) => (r.id === id ? { ...r, campus } : r)));
  }

  function updateCount(id: string, monthIdx: number, raw: string) {
    setDirty(true);
    setEditRows((prev) =>
      prev.map((r) => {
        if (r.id !== id) return r;
        const counts = [...r.counts];
        counts[monthIdx] = parseCount(raw);
        return { ...r, counts };
      })
    );
  }

  function removeRow(id: string) {
    setDirty(true);
    setEditRows((prev) => prev.filter((r) => r.id !== id));
  }

  function resetEdits() {
    setEditRows(boardToEditRows(board));
    setDirty(false);
  }

  function exportCsv() {
    const headers = ["Campus", ...months.map((m) => m.label), "Total"];
    const lines = [headers.map(csvEscape).join(",")];
    for (const row of summary.rows) {
      lines.push(
        [row.campus, ...row.counts.map((n) => String(n)), String(row.total)].map(csvEscape).join(",")
      );
    }
    lines.push(
      ["All campuses", ...summary.totals.map((n) => String(n)), String(summary.grand_total)]
        .map(csvEscape)
        .join(",")
    );
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${platform}-campus-uploads.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

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
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-zinc-500">
            {HINT[platform]} Edit any cell, delete bad rows, then Export — changes stay on this screen
            until you reset or refresh.
          </p>
        </div>
        <div className="flex w-full flex-col gap-2 sm:flex-row sm:items-center sm:justify-end lg:w-auto">
          <label className="flex h-9 w-full max-w-xs items-center gap-2 rounded-xl border border-white/10 bg-black/40 px-3">
            <Search size={14} className="shrink-0 text-zinc-500" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter campus…"
              className="w-full bg-transparent text-sm outline-none placeholder:text-zinc-600"
            />
          </label>
          <button
            type="button"
            onClick={resetEdits}
            disabled={!dirty || !board}
            className="inline-flex h-9 items-center justify-center gap-1.5 rounded-xl border border-white/10 bg-black px-3 text-xs font-medium text-zinc-300 hover:border-white/20 disabled:opacity-40"
          >
            <RotateCcw size={14} />
            Reset
          </button>
          <button
            type="button"
            onClick={exportCsv}
            disabled={!summary.rows.length}
            className="inline-flex h-9 items-center justify-center gap-1.5 rounded-xl border border-white/10 bg-black px-3 text-xs font-medium text-zinc-300 hover:border-[#ff3b30]/40 hover:text-white disabled:opacity-40"
          >
            <Download size={14} />
            Export CSV
          </button>
        </div>
      </div>

      {months.length > 0 && editRows.length >= 0 && board ? (
        <div className="grid gap-px border-b border-white/[0.06] bg-white/[0.04] sm:grid-cols-3">
          <div className="bg-[#121212] px-5 py-3">
            <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">Total uploads</div>
            <div className="mt-1 text-2xl font-semibold tabular">{formatNumber(summary.grand_total)}</div>
          </div>
          <div className="bg-[#121212] px-5 py-3">
            <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">Campuses</div>
            <div className="mt-1 text-2xl font-semibold tabular">{formatNumber(summary.rows.length)}</div>
          </div>
          <div className="bg-[#121212] px-5 py-3">
            <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">
              {thisMonth?.label || "This month"}
            </div>
            <div className="mt-1 text-2xl font-semibold tabular text-[#ff3b30]">
              {formatNumber(thisMonthTotal)}
            </div>
          </div>
        </div>
      ) : null}

      {query.isPending && !data ? (
        <div className="h-48 animate-pulse bg-zinc-900/60" />
      ) : query.error ? (
        <p className="px-5 py-8 text-sm text-rose-300">{(query.error as Error).message}</p>
      ) : !months.length || (!editRows.length && !board?.rows.length) ? (
        <p className="px-5 py-8 text-sm text-zinc-500">No uploads in the programme window yet.</p>
      ) : !editRows.length ? (
        <p className="px-5 py-8 text-sm text-zinc-500">
          All campus rows were removed. Reset to bring the original table back, or Export an empty
          file after adding nothing.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full table-fixed border-collapse text-left text-sm">
            <colgroup>
              <col className="w-[280px]" />
              {months.map((m) => (
                <col key={m.id} className="w-[104px]" />
              ))}
              <col className="w-[96px]" />
              <col className="w-[52px]" />
            </colgroup>
            <thead className="sticky top-0 z-10 bg-[#1a1a1a]">
              <tr className="border-b border-white/10 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-400">
                <th className="sticky left-0 z-20 bg-[#1a1a1a] px-4 py-3 text-left">Campus</th>
                {months.map((m) => (
                  <th key={m.id} className="px-2 py-3 text-center">
                    {m.label}
                  </th>
                ))}
                <th className="px-3 py-3 text-right">Total</th>
                <th className="px-2 py-3 text-center">
                  <span className="sr-only">Remove</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr
                  key={row.id}
                  className={cn(
                    "border-b border-white/[0.04]",
                    idx % 2 === 0 ? "bg-black/20" : "bg-transparent"
                  )}
                >
                  <td className="sticky left-0 z-10 bg-[#121212] px-4 py-2 align-middle">
                    <input
                      value={row.campus}
                      onChange={(e) => updateCampus(row.id, e.target.value)}
                      className="box-border h-9 w-full rounded-lg border border-white/10 bg-black/40 px-2.5 text-sm font-medium text-zinc-100 outline-none focus:border-[#ff3b30]/50"
                      aria-label="Campus name"
                    />
                  </td>
                  {row.counts.map((n, i) => (
                    <td key={months[i]?.id || i} className="px-2 py-2 text-center align-middle">
                      <input
                        type="text"
                        inputMode="numeric"
                        value={String(n)}
                        onChange={(e) => updateCount(row.id, i, e.target.value)}
                        className={cn(
                          "box-border mx-auto block h-9 w-full max-w-[4.5rem] rounded-lg border border-white/10 px-2 text-center text-sm tabular outline-none focus:border-[#ff3b30]/50 focus:bg-black/50",
                          heatClass(n, maxCell)
                        )}
                        aria-label={`${row.campus} ${months[i]?.label || "month"}`}
                      />
                    </td>
                  ))}
                  <td className="px-3 py-2 text-right align-middle">
                    <div className="flex h-9 flex-col items-end justify-center gap-1">
                      <span className="leading-none font-semibold tabular">{formatNumber(row.total)}</span>
                      <span className="h-1 w-14 overflow-hidden rounded-full bg-white/10">
                        <span
                          className="block h-full rounded-full bg-gradient-to-r from-[#f58529] to-[#dd2a7b]"
                          style={{
                            width: `${Math.min(
                              100,
                              summary.grand_total ? (row.total / summary.grand_total) * 100 : 0
                            )}%`,
                          }}
                        />
                      </span>
                    </div>
                  </td>
                  <td className="px-2 py-2 text-center align-middle">
                    <button
                      type="button"
                      onClick={() => removeRow(row.id)}
                      className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 text-zinc-500 hover:border-rose-500/40 hover:text-rose-300"
                      title="Remove row"
                      aria-label={`Remove ${row.campus}`}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-white/10 bg-[#161616]">
                <td className="sticky left-0 bg-[#161616] px-4 py-3 font-semibold align-middle">
                  All campuses
                </td>
                {summary.totals.map((n, i) => (
                  <td
                    key={months[i]?.id || i}
                    className="px-2 py-3 text-center font-semibold tabular align-middle"
                  >
                    {formatNumber(n)}
                  </td>
                ))}
                <td className="px-3 py-3 text-right text-base font-semibold tabular text-[#ff3b30] align-middle">
                  {formatNumber(summary.grand_total)}
                </td>
                <td className="px-2 py-3" />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
