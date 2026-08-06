"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import { AlertCircle, Download, Plus, RefreshCw, Search } from "lucide-react";
import { api, type Profile } from "@/lib/api";
import { cn, formatNumber, formatPct } from "@/lib/utils";
import { SparkAvatar } from "@/components/spark/ui";

type ListResponse = { items: Profile[]; total: number; page: number; page_size: number };

const STATUS_FILTERS = [
  { id: "", label: "All" },
  { id: "active", label: "Active" },
  { id: "failed", label: "Failed" },
  { id: "paused", label: "Paused" },
] as const;

export default function AdminScrapingPage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [ig, setIg] = useState("");
  const [studentId, setStudentId] = useState("");
  const [fullName, setFullName] = useState("");
  const [university, setUniversity] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ q, page: String(page), page_size: "20" });
    if (statusFilter) params.set("status", statusFilter);
    return params.toString();
  }, [q, page, statusFilter]);

  const { data, isLoading } = useQuery({
    queryKey: ["profiles", q, page, statusFilter],
    queryFn: () => api<ListResponse>(`/profiles?${queryString}`),
  });

  const add = useMutation({
    mutationFn: () =>
      api<Profile>("/profiles", {
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
      }),
    onSuccess: () => {
      setIg("");
      setStudentId("");
      setFullName("");
      setUniversity("");
      setError("");
      qc.invalidateQueries({ queryKey: ["profiles"] });
      qc.invalidateQueries({ queryKey: ["spark"] });
    },
    onError: (e: Error) => setError(e.message),
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
        return;
      }
      await api(`/profiles/bulk/${action}`, { method: "POST", body: JSON.stringify({ ids: selected }) });
    },
    onSuccess: () => {
      setSelected([]);
      qc.invalidateQueries({ queryKey: ["profiles"] });
      qc.invalidateQueries({ queryKey: ["spark"] });
    },
    onError: (e: Error) => setError(e.message),
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

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Scraping / Creators</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Admins only. Add creators with <span className="text-zinc-300">Student ID + Instagram</span>, then scrape.
            That pair is what students use to log in.
          </p>
        </div>
        <Link
          href="/admin-import"
          className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-[#121212] px-4 py-2 text-sm text-zinc-300 hover:border-[#ff3b30]/40 hover:text-white"
        >
          Bulk roster import →
        </Link>
      </div>

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
      </form>

      <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <label className="relative w-full max-w-sm shrink">
              <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500" />
              <input
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setPage(1);
                }}
                placeholder="Search name, student ID, campus, @handle…"
                className="w-full rounded-full border border-white/10 bg-black py-2.5 pl-10 pr-4 text-sm outline-none focus:border-[#ff3b30]"
              />
            </label>
            <div className="flex shrink-0 flex-nowrap items-center gap-1">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.id || "all"}
                  type="button"
                  onClick={() => {
                    setStatusFilter(f.id);
                    setPage(1);
                  }}
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
                  <th className="px-2 py-3">Posts</th>
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
                          initials={(p.student?.full_name || p.full_name || p.username || "?").slice(0, 2).toUpperCase()}
                          size="sm"
                        />
                        <div>
                          <div className="font-medium">{p.student?.full_name || p.full_name || p.username}</div>
                          <div className="text-[11px] text-zinc-500">@{p.username}</div>
                          {p.status === "failed" && (
                            <div className="mt-0.5 flex items-center gap-1 text-[11px] text-rose-400">
                              <AlertCircle size={11} /> Scrape failed
                            </div>
                          )}
                        </div>
                      </Link>
                    </td>
                    <td className="px-2 py-3 tabular text-zinc-300">{p.student?.student_id || "—"}</td>
                    <td className="px-2 py-3 text-zinc-400">{p.student?.university || "—"}</td>
                    <td className="px-2 py-3 tabular">{formatNumber(p.followers)}</td>
                    <td className="px-2 py-3 tabular text-zinc-400">{formatNumber(p.posts_count)}</td>
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
                          p.status === "active" && "bg-lime-500/15 text-lime-400",
                          p.status === "failed" && "bg-rose-500/15 text-rose-400",
                          p.status === "paused" && "bg-amber-500/15 text-amber-400"
                        )}
                      >
                        {p.status}
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

        <div className="mt-4 flex items-center justify-between text-xs text-zinc-500">
          <span>{data?.total || 0} creators · {selected.length} selected</span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="rounded-lg border border-white/10 px-3 py-1.5 disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={!data || page * data.page_size >= data.total}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-lg border border-white/10 px-3 py-1.5 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
