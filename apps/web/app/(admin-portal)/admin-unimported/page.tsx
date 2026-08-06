"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Download, Trash2 } from "lucide-react";
import {
  clearUnimported,
  downloadUnimportedCsv,
  loadUnimported,
  type UnimportedItem,
} from "@/lib/import-unimported";
import { cn } from "@/lib/utils";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "missing_instagram", label: "Missing IG" },
  { id: "duplicate_in_sheet", label: "Sheet dupes" },
  { id: "failed", label: "Failed" },
  { id: "skipped", label: "Skipped" },
] as const;

export default function AdminUnimportedPage() {
  const [items, setItems] = useState<UnimportedItem[]>([]);
  const [ready, setReady] = useState(false);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("all");

  useEffect(() => {
    setItems(loadUnimported());
    setReady(true);
  }, []);

  const filtered = useMemo(() => {
    if (filter === "all") return items;
    return items.filter((i) => i.reason_code === filter);
  }, [items, filter]);

  if (!ready) return <div className="h-48 animate-pulse rounded-2xl bg-zinc-900" />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/admin-import" className="text-xs text-zinc-500 hover:text-zinc-300">
            ← Import roster
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">Unimported rows</h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-500">
            Sheet lines that did not become new profiles — missing Instagram, invalid handles, duplicate
            usernames in the sheet, or API skip/fail. Fix these in Excel and re-import.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {items.length > 0 && (
            <>
              <button
                type="button"
                onClick={() => downloadUnimportedCsv(filtered)}
                className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-[#121212] px-3 py-2 text-sm hover:border-white/25"
              >
                <Download size={14} /> Export CSV
              </button>
              <button
                type="button"
                onClick={() => {
                  clearUnimported();
                  setItems([]);
                }}
                className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-[#121212] px-3 py-2 text-sm hover:border-rose-500/40"
              >
                <Trash2 size={14} /> Clear list
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            className={cn(
              "rounded-full px-3 py-1.5 text-xs font-medium",
              filter === f.id ? "bg-white text-black" : "bg-zinc-900 text-zinc-400"
            )}
          >
            {f.label}
            {f.id === "all" ? ` (${items.length})` : ""}
          </button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
        {!filtered.length ? (
          <p className="py-8 text-center text-sm text-zinc-500">
            No unimported rows yet. Load a roster sheet on Import — dropped lines appear here automatically.
          </p>
        ) : (
          <table className="w-full min-w-[960px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-wide text-zinc-500">
                <th className="pb-3 pr-3 font-medium">Row</th>
                <th className="pb-3 pr-3 font-medium">Name</th>
                <th className="pb-3 pr-3 font-medium">Student ID</th>
                <th className="pb-3 pr-3 font-medium">Instagram (raw)</th>
                <th className="pb-3 pr-3 font-medium">Reason</th>
                <th className="pb-3 font-medium">When</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr key={item.id} className="border-b border-white/[0.04]">
                  <td className="py-2.5 pr-3 tabular text-zinc-500">{item.row_number ?? "—"}</td>
                  <td className="py-2.5 pr-3 font-medium">{item.full_name || "—"}</td>
                  <td className="py-2.5 pr-3 text-zinc-300">{item.student_id || "—"}</td>
                  <td className="max-w-[220px] truncate py-2.5 pr-3 text-zinc-500" title={item.raw_instagram || item.url}>
                    {item.username ? `@${item.username}` : item.raw_instagram || item.url || "—"}
                  </td>
                  <td className="py-2.5 pr-3 text-amber-300/90">{item.reason}</td>
                  <td className="whitespace-nowrap py-2.5 text-xs text-zinc-500">
                    {new Date(item.recorded_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <p className="text-xs text-zinc-600">
        Also see{" "}
        <Link href="/admin-duplicates" className="text-zinc-400 underline hover:text-white">
          Duplicates
        </Link>{" "}
        for accounts that were already tracked (those did import/merge, they are not “missing”).
      </p>
    </div>
  );
}
