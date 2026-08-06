"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import {
  clearImportDuplicates,
  loadImportDuplicates,
  type ImportDuplicateItem,
} from "@/lib/import-duplicates";

export default function AdminDuplicatesPage() {
  const [items, setItems] = useState<ImportDuplicateItem[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setItems(loadImportDuplicates());
    setReady(true);
  }, []);

  if (!ready) return <div className="h-48 animate-pulse rounded-2xl bg-zinc-900" />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/admin-import" className="text-xs text-zinc-500 hover:text-zinc-300">
            ← Import roster
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">Duplicates</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Accounts already tracked when you re-imported a sheet. Scrapes were skipped for profiles that already
            succeeded.
          </p>
        </div>
        {items.length > 0 && (
          <button
            type="button"
            onClick={() => {
              clearImportDuplicates();
              setItems([]);
            }}
            className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-[#121212] px-3 py-2 text-sm hover:border-rose-500/40"
          >
            <Trash2 size={14} /> Clear list
          </button>
        )}
      </div>

      <div className="overflow-x-auto rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
        {!items.length ? (
          <p className="py-8 text-center text-sm text-zinc-500">
            No duplicates yet. When you re-import a sheet, existing accounts appear here.
          </p>
        ) : (
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-wide text-zinc-500">
                <th className="pb-3 pr-3 font-medium">Username</th>
                <th className="pb-3 pr-3 font-medium">Source URL</th>
                <th className="pb-3 pr-3 font-medium">Note</th>
                <th className="pb-3 pr-3 font-medium">When</th>
                <th className="pb-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={`${item.profile_id || item.url}-${item.imported_at}`} className="border-b border-white/[0.04]">
                  <td className="py-2.5 pr-3 font-medium">@{item.username || "—"}</td>
                  <td className="max-w-[240px] truncate py-2.5 pr-3 text-zinc-500" title={item.url}>
                    {item.url}
                  </td>
                  <td className="py-2.5 pr-3 text-zinc-500">{item.message || "Already tracked"}</td>
                  <td className="whitespace-nowrap py-2.5 pr-3 text-xs text-zinc-500">
                    {new Date(item.imported_at).toLocaleString()}
                  </td>
                  <td className="py-2.5">
                    {item.profile_id ? (
                      <Link href={`/admin-scraping/${item.profile_id}`} className="text-[#ff3b30] hover:underline">
                        View creator
                      </Link>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
