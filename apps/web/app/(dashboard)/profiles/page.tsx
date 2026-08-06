"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import { AlertCircle, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, EmptyState } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, type Profile } from "@/lib/api";
import { STUDENT_SHEET_COLUMNS, studentFieldValue } from "@/lib/student-fields";
import { formatNumber, formatPct, humanizeScrapeError, cn } from "@/lib/utils";
import { Avatar } from "@/components/ui/avatar";

type ListResponse = { items: Profile[]; total: number; page: number; page_size: number };

const STATUS_FILTERS = [
  { id: "", label: "All" },
  { id: "active", label: "Active" },
  { id: "failed", label: "Failed" },
  { id: "paused", label: "Paused" },
] as const;

/** Sheet columns shown in the list table (subset for width; all fields on detail page). */
const LIST_STUDENT_COLS = STUDENT_SHEET_COLUMNS.filter((c) =>
  [
    "program",
    "year_of_study",
    "email",
    "mobile",
    "instagram_handle",
    "instagram_username",
    "youtube_link",
    "created_content_before",
    "instagram_followers_declared",
    "content_interest",
    "uid",
  ].includes(c.key)
);

function statusBadgeClass(status: string) {
  if (status === "failed" || status === "unavailable") return "badge-danger";
  if (status === "active") return "badge-success";
  if (status === "paused") return "badge-warning";
  return "badge-neutral";
}

export default function ProfilesPage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [url, setUrl] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({
      q,
      page: String(page),
      page_size: "20",
    });
    if (statusFilter) params.set("status", statusFilter);
    return params.toString();
  }, [q, page, statusFilter]);

  const { data, isLoading } = useQuery({
    queryKey: ["profiles", q, page, statusFilter],
    queryFn: () => api<ListResponse>(`/profiles?${queryString}`),
  });

  const add = useMutation({
    mutationFn: () => api<Profile>("/profiles", { method: "POST", body: JSON.stringify({ url }) }),
    onSuccess: () => {
      setUrl("");
      setError("");
      qc.invalidateQueries({ queryKey: ["profiles"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const bulk = useMutation({
    mutationFn: async (action: "refresh" | "delete" | "pause" | "resume" | "export") => {
      if (action === "export") {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/profiles/bulk/export`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("is_access_token")}`,
          },
          body: JSON.stringify({ ids: selected }),
        });
        const blob = await res.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "instascope-profiles.csv";
        a.click();
        return;
      }
      await api(`/profiles/bulk/${action}`, { method: "POST", body: JSON.stringify({ ids: selected }) });
    },
    onSuccess: () => {
      setSelected([]);
      qc.invalidateQueries({ queryKey: ["profiles"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });

  const allIds = useMemo(() => data?.items.map((p) => p.id) || [], [data]);

  function onAdd(e: FormEvent) {
    e.preventDefault();
    add.mutate();
  }

  return (
    <div className="space-y-7">
      <Card padding="lg" className="relative overflow-hidden">
        <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-accent/[0.06]" />
        <div className="relative">
          <div className="text-sm font-semibold tracking-tight">Add a profile</div>
          <p className="mt-1 text-sm text-muted">Supports full URLs or @usernames.</p>
          <form onSubmit={onAdd} className="mt-4 flex flex-col gap-3 sm:flex-row">
            <Input
              className="flex-1"
              placeholder="https://instagram.com/cristiano"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <Button type="submit" disabled={add.isPending || !url.trim()} className="sm:min-w-[120px]">
              <Plus size={16} />
              {add.isPending ? "Scraping…" : "Add"}
            </Button>
          </form>
          {error && <p className="mt-3 text-sm text-danger">{error}</p>}
        </div>
      </Card>

      <Card padding="lg">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative max-w-sm w-full">
              <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                className="pl-10"
                placeholder="Search username, name, student ID, university…"
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setPage(1);
                }}
              />
            </div>
            <div className="flex flex-wrap gap-1">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => {
                    setStatusFilter(f.id);
                    setPage(1);
                  }}
                  className={cn(
                    "rounded-full px-3 py-1.5 text-xs font-medium transition",
                    statusFilter === f.id ? "bg-fg text-white" : "bg-slate-100 text-muted hover:text-fg"
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
                ["refresh", "Refresh"],
                ["pause", "Pause"],
                ["resume", "Resume"],
                ["export", "Export"],
              ] as const
            ).map(([action, label]) => (
              <Button
                key={action}
                size="sm"
                variant="secondary"
                disabled={!selected.length || bulk.isPending}
                onClick={() => bulk.mutate(action)}
              >
                {label}
              </Button>
            ))}
            <Button size="sm" variant="danger" disabled={!selected.length || bulk.isPending} onClick={() => bulk.mutate("delete")}>
              Delete
            </Button>
          </div>
        </div>

        <div className="mt-6 overflow-x-auto">
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-14 skeleton" />
              ))}
            </div>
          ) : !data?.items.length ? (
            <EmptyState
              title="No profiles yet"
              description="Add your first Instagram profile above to begin continuous monitoring."
            />
          ) : (
            <table className="table-premium min-w-[1800px]">
              <thead>
                <tr>
                  <th className="w-10">
                    <input
                      type="checkbox"
                      className="rounded border-slate-300"
                      checked={!!allIds.length && selected.length === allIds.length}
                      onChange={(e) => setSelected(e.target.checked ? allIds : [])}
                    />
                  </th>
                  <th>Username</th>
                  <th>Full name</th>
                  <th>Student ID</th>
                  <th>University</th>
                  {LIST_STUDENT_COLS.map((col) => (
                    <th key={col.key}>{col.label}</th>
                  ))}
                  <th>Followers</th>
                  <th>Following</th>
                  <th>Posts</th>
                  <th>Avg likes</th>
                  <th>Growth</th>
                  <th>Status</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((p) => (
                  <tr
                    key={p.id}
                    className={cn(p.status === "failed" && "bg-red-50/80 hover:bg-red-50")}
                    title={p.status === "failed" && p.last_error ? humanizeScrapeError(p.last_error) : undefined}
                  >
                    <td>
                      <input
                        type="checkbox"
                        className="rounded border-slate-300"
                        checked={selected.includes(p.id)}
                        onChange={(e) =>
                          setSelected((prev) => (e.target.checked ? [...prev, p.id] : prev.filter((id) => id !== p.id)))
                        }
                      />
                    </td>
                    <td>
                      <Link href={`/profiles/${p.id}`} className="group flex items-center gap-3">
                        <Avatar name={p.username} size="md" />
                        <div>
                          <div className="font-medium group-hover:text-accent transition">@{p.username}</div>
                          {p.status === "failed" && (
                            <div className="mt-0.5 flex items-center gap-1 text-xs text-danger">
                              <AlertCircle size={11} /> Needs refresh
                            </div>
                          )}
                          {p.status === "unavailable" && (
                            <div className="mt-0.5 flex items-center gap-1 text-xs text-amber-700">
                              <AlertCircle size={11} /> Doesn&apos;t exist
                            </div>
                          )}
                        </div>
                      </Link>
                    </td>
                    <td className="text-sm">{p.student?.full_name || p.full_name || "—"}</td>
                    <td className="text-sm text-muted">{p.student?.student_id || "—"}</td>
                    <td className="text-sm text-muted max-w-[140px] truncate" title={p.student?.university || ""}>
                      {p.student?.university || "—"}
                    </td>
                    {LIST_STUDENT_COLS.map((col) => (
                      <td
                        key={col.key}
                        className="max-w-[140px] truncate text-sm text-muted"
                        title={studentFieldValue(p.student, col.key)}
                      >
                        {studentFieldValue(p.student, col.key) || "—"}
                      </td>
                    ))}
                    <td className="tabular font-medium">{formatNumber(p.followers)}</td>
                    <td className="tabular text-muted">{formatNumber(p.following)}</td>
                    <td className="tabular text-muted">{formatNumber(p.posts_count)}</td>
                    <td className="tabular font-medium">{formatNumber(p.avg_likes)}</td>
                    <td className={`tabular font-medium ${p.growth_pct_today >= 0 ? "text-success" : "text-danger"}`}>
                      {formatPct(p.growth_pct_today)}
                    </td>
                    <td>
                      <div className="flex flex-col gap-0.5">
                        <span className={statusBadgeClass(p.status)}>{p.status}</span>
                        {p.status === "failed" && p.last_error && (
                          <span className="max-w-[160px] truncate text-[10px] leading-tight text-danger/80" title={humanizeScrapeError(p.last_error)}>
                            {humanizeScrapeError(p.last_error)}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="text-xs text-muted whitespace-nowrap">
                      {p.last_scraped_at ? new Date(p.last_scraped_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="mt-5 flex items-center justify-between border-t border-border pt-4 text-sm text-muted">
          <span className="tabular">{data?.total || 0} profiles</span>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={!data || page * data.page_size >= data.total}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
