"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus, Search, ShieldOff, UserPlus } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type AccessStatus = "has_access" | "incomplete" | "blocked";
type AccessFilter = "all" | "has_access" | "no_access" | "incomplete" | "blocked";

type AccessRow = {
  profile_id: string;
  full_name: string;
  student_id: string;
  instagram_username: string;
  campus: string;
  access: AccessStatus;
  has_account: boolean;
  is_active: boolean | null;
};

type AccessList = {
  items: AccessRow[];
  total: number;
  page: number;
  page_size: number;
  counts: Record<string, number>;
};

const FILTERS: { id: AccessFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "has_access", label: "Has access" },
  { id: "no_access", label: "No access" },
  { id: "incomplete", label: "Missing credentials" },
  { id: "blocked", label: "Revoked" },
];

function accessLabel(row: AccessRow) {
  if (row.access === "blocked") return "Revoked";
  if (row.access === "incomplete") return "Incomplete";
  if (row.has_account) return "Has access";
  return "Can log in";
}

function CredentialField({
  value,
  prefix,
  disabled,
  onSave,
}: {
  value: string;
  prefix?: string;
  disabled?: boolean;
  onSave: (next: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  async function commit() {
    const next = draft.trim();
    if (!next || next === value || saving || disabled) {
      if (!next) setDraft(value);
      return;
    }
    setSaving(true);
    try {
      await onSave(next);
    } catch {
      setDraft(value);
    } finally {
      setSaving(false);
    }
  }

  return (
    <label className="flex min-w-[140px] items-center rounded-lg border border-transparent bg-transparent px-1.5 py-1 focus-within:border-white/20 focus-within:bg-black/40">
      {prefix ? <span className="pr-0.5 text-zinc-500">{prefix}</span> : null}
      <input
        value={draft}
        disabled={disabled || saving}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => void commit()}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.currentTarget.blur();
          }
          if (e.key === "Escape") {
            setDraft(value);
            e.currentTarget.blur();
          }
        }}
        className="w-full min-w-0 bg-transparent text-sm text-zinc-100 outline-none disabled:text-zinc-500"
      />
    </label>
  );
}

export default function AdminAccessPage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [access, setAccess] = useState<AccessFilter>("all");
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({
    full_name: "",
    student_id: "",
    instagram_username: "",
    university: "",
    grant: true,
  });
  const [message, setMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q), 280);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    setPage(1);
  }, [qDebounced, access]);

  const query = useQuery({
    queryKey: ["spark", "student-access", qDebounced, access, page],
    queryFn: () => {
      const params = new URLSearchParams({
        access,
        page: String(page),
        page_size: "50",
      });
      if (qDebounced.trim()) params.set("q", qDebounced.trim());
      return api<AccessList>(`/spark/admin/student-access?${params}`);
    },
  });

  const data = query.data;
  const counts = data?.counts || {};

  const patch = useMutation({
    mutationFn: (payload: { profile_id: string } & Record<string, unknown>) => {
      const { profile_id, ...body } = payload;
      return api<AccessRow>(`/spark/admin/student-access/${profile_id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["spark", "student-access"] });
      setMessage({ type: "ok", text: "Saved to the database. Login credentials update immediately." });
    },
    onError: (err: Error) => setMessage({ type: "err", text: err.message }),
  });

  const create = useMutation({
    mutationFn: () =>
      api<AccessRow>("/spark/admin/student-access", {
        method: "POST",
        body: JSON.stringify(createForm),
      }),
    onSuccess: (row) => {
      void qc.invalidateQueries({ queryKey: ["spark", "student-access"] });
      setShowCreate(false);
      setCreateForm({
        full_name: "",
        student_id: "",
        instagram_username: "",
        university: "",
        grant: true,
      });
      setMessage({
        type: "ok",
        text: `Access ready for ${row.full_name || row.student_id}. They sign in with admission number + Instagram.`,
      });
    },
    onError: (err: Error) => setMessage({ type: "err", text: err.message }),
  });

  const pages = Math.max(1, Math.ceil((data?.total || 0) / (data?.page_size || 50)));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-[#ff3b30]">
            <KeyRound size={16} />
            <span className="text-[11px] font-semibold uppercase tracking-[0.16em]">Credentials</span>
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">Student access</h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-500">
            Admission number + Instagram handle are the login credentials. Edit a cell and it writes to Mongo
            immediately — the student uses the new values on the next sign-in.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowCreate((v) => !v)}
          className="inline-flex items-center gap-2 rounded-xl bg-[#ff3b30] px-3.5 py-2 text-sm font-medium text-white hover:bg-[#ff5248]"
        >
          <Plus size={15} /> Create access
        </button>
      </div>

      {message ? (
        <div
          className={cn(
            "rounded-xl border px-4 py-3 text-sm",
            message.type === "ok"
              ? "border-emerald-500/20 bg-emerald-500/[0.08] text-emerald-200"
              : "border-rose-500/20 bg-rose-500/[0.08] text-rose-200"
          )}
        >
          {message.text}
        </div>
      ) : null}

      {showCreate ? (
        <form
          className="grid gap-3 rounded-2xl border border-white/[0.08] bg-[#121212] p-5 md:grid-cols-2 lg:grid-cols-5"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <label className="text-xs text-zinc-500 lg:col-span-1">
            Full name
            <input
              required
              value={createForm.full_name}
              onChange={(e) => setCreateForm((f) => ({ ...f, full_name: e.target.value }))}
              className="mt-1 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white outline-none focus:border-white/25"
            />
          </label>
          <label className="text-xs text-zinc-500">
            Admission number
            <input
              required
              value={createForm.student_id}
              onChange={(e) => setCreateForm((f) => ({ ...f, student_id: e.target.value }))}
              className="mt-1 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white outline-none focus:border-white/25"
            />
          </label>
          <label className="text-xs text-zinc-500">
            Instagram
            <input
              required
              placeholder="@handle"
              value={createForm.instagram_username}
              onChange={(e) => setCreateForm((f) => ({ ...f, instagram_username: e.target.value }))}
              className="mt-1 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white outline-none focus:border-white/25"
            />
          </label>
          <label className="text-xs text-zinc-500">
            Campus
            <input
              value={createForm.university}
              onChange={(e) => setCreateForm((f) => ({ ...f, university: e.target.value }))}
              className="mt-1 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white outline-none focus:border-white/25"
            />
          </label>
          <div className="flex items-end gap-2">
            <label className="flex h-[42px] items-center gap-2 text-xs text-zinc-400">
              <input
                type="checkbox"
                checked={createForm.grant}
                onChange={(e) => setCreateForm((f) => ({ ...f, grant: e.target.checked }))}
              />
              Grant login
            </label>
            <button
              type="submit"
              disabled={create.isPending}
              className="inline-flex h-[42px] flex-1 items-center justify-center gap-2 rounded-xl bg-white px-3 text-sm font-medium text-black disabled:opacity-50"
            >
              <UserPlus size={14} />
              {create.isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      ) : null}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative min-w-0 flex-1">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search name, admission number, Instagram…"
            className="w-full rounded-xl border border-white/10 bg-[#121212] py-2.5 pl-9 pr-3 text-sm outline-none placeholder:text-zinc-600 focus:border-white/25"
          />
        </div>
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setAccess(f.id)}
              className={cn(
                "rounded-full px-3 py-1.5 text-xs font-medium",
                access === f.id ? "bg-white text-black" : "bg-zinc-900 text-zinc-400 hover:text-zinc-200"
              )}
            >
              {f.label}
              {typeof counts[f.id] === "number" ? ` (${counts[f.id]})` : ""}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
        {query.isLoading ? (
          <div className="h-40 animate-pulse rounded-xl bg-white/[0.04]" />
        ) : query.error ? (
          <p className="py-8 text-center text-sm text-rose-300">
            {(query.error as Error).message || "Could not load student access"}
          </p>
        ) : !data?.items.length ? (
          <p className="py-8 text-center text-sm text-zinc-500">
            No students match this search. Create access or import a roster first.
          </p>
        ) : (
          <table className="w-full min-w-[920px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-wide text-zinc-500">
                <th className="pb-3 pr-3 font-medium">Student</th>
                <th className="pb-3 pr-3 font-medium">Admission number</th>
                <th className="pb-3 pr-3 font-medium">Instagram</th>
                <th className="pb-3 pr-3 font-medium">Campus</th>
                <th className="pb-3 pr-3 font-medium">Access</th>
                <th className="pb-3 font-medium"> </th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => (
                <tr key={row.profile_id} className="border-b border-white/[0.04]">
                  <td className="py-2 pr-3">
                    <div className="font-medium text-zinc-100">{row.full_name || "—"}</div>
                    {row.has_account ? (
                      <div className="text-[11px] text-zinc-500">Account created</div>
                    ) : row.access === "has_access" ? (
                      <div className="text-[11px] text-zinc-500">First login will create the account</div>
                    ) : null}
                  </td>
                  <td className="py-2 pr-3">
                    <CredentialField
                      value={row.student_id}
                      disabled={patch.isPending}
                      onSave={async (student_id) => {
                        await patch.mutateAsync({ profile_id: row.profile_id, student_id });
                      }}
                    />
                  </td>
                  <td className="py-2 pr-3">
                    <CredentialField
                      value={row.instagram_username}
                      prefix="@"
                      disabled={patch.isPending}
                      onSave={async (instagram_username) => {
                        await patch.mutateAsync({
                          profile_id: row.profile_id,
                          instagram_username,
                        });
                      }}
                    />
                  </td>
                  <td className="max-w-[180px] truncate py-2 pr-3 text-zinc-400">{row.campus || "—"}</td>
                  <td className="py-2 pr-3">
                    <span
                      className={cn(
                        "inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium",
                        row.access === "has_access" && "bg-emerald-500/15 text-emerald-300",
                        row.access === "incomplete" && "bg-amber-500/15 text-amber-200",
                        row.access === "blocked" && "bg-rose-500/15 text-rose-300"
                      )}
                    >
                      {accessLabel(row)}
                    </span>
                  </td>
                  <td className="py-2">
                    {row.access === "blocked" ? (
                      <button
                        type="button"
                        disabled={patch.isPending}
                        onClick={() => patch.mutate({ profile_id: row.profile_id, access: "grant" })}
                        className="text-xs text-emerald-300 hover:underline disabled:opacity-50"
                      >
                        Restore
                      </button>
                    ) : row.access === "has_access" ? (
                      <button
                        type="button"
                        disabled={patch.isPending}
                        onClick={() => patch.mutate({ profile_id: row.profile_id, access: "revoke" })}
                        className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-rose-300 disabled:opacity-50"
                      >
                        <ShieldOff size={12} /> Revoke
                      </button>
                    ) : (
                      <button
                        type="button"
                        disabled={patch.isPending || !row.student_id || !row.instagram_username}
                        onClick={() => patch.mutate({ profile_id: row.profile_id, access: "grant" })}
                        className="text-xs text-zinc-300 hover:underline disabled:opacity-40"
                      >
                        Grant
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {data && data.total > (data.page_size || 50) ? (
        <div className="flex items-center justify-between text-xs text-zinc-500">
          <span>
            {data.total} students · page {data.page} of {pages}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded-lg border border-white/10 px-3 py-1.5 disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={page >= pages}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-lg border border-white/10 px-3 py-1.5 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
