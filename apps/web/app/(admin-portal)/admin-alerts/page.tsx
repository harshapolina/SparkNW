"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bell } from "lucide-react";
import { api } from "@/lib/api";
import type { AdminOverviewResponse } from "@/lib/spark/api-types";
import { cn } from "@/lib/utils";

type Notification = {
  id: string;
  type: string;
  title: string;
  body: string;
  is_read: boolean;
  created_at: string;
  profile_id?: string | null;
};

export default function AdminAlertsPage() {
  const qc = useQueryClient();
  const adminQ = useQuery({
    queryKey: ["spark", "admin"],
    queryFn: () => api<AdminOverviewResponse>("/spark/admin"),
  });
  const notifQ = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<Notification[]>("/notifications"),
  });

  const markAll = useMutation({
    mutationFn: () => api("/notifications/read-all", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const live = adminQ.data?.alerts || [];
  const notifs = notifQ.data || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link href="/admin-dashboard" className="text-xs text-zinc-500 hover:text-zinc-300">
            ← Dashboard
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">Alerts & notifications</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Scrape failures, private accounts, growth swings, and stored notification history.
          </p>
        </div>
        <button
          type="button"
          disabled={markAll.isPending}
          onClick={() => markAll.mutate()}
          className="rounded-xl border border-white/10 bg-[#121212] px-4 py-2 text-sm hover:border-[#ff3b30]/40 disabled:opacity-60"
        >
          Mark all notifications read
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-2xl border border-rose-500/20 bg-[#121212] p-5">
          <div className="mb-4 flex items-center gap-2">
            <AlertTriangle size={16} className="text-rose-400" />
            <h2 className="text-sm font-semibold">Live portfolio alerts</h2>
            <span className="text-xs text-zinc-500">{live.length}</span>
          </div>
          <ul className="space-y-2">
            {live.map((a) => (
              <li key={a.id}>
                <Link
                  href={`/admin-scraping/${a.profile_id}`}
                  className="block rounded-xl border border-white/[0.04] bg-black/40 px-3 py-3 hover:border-rose-500/30"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="text-sm font-medium">{a.title}</div>
                    <span
                      className={cn(
                        "shrink-0 rounded-full px-2 py-0.5 text-[10px] uppercase",
                        a.severity === "high" ? "bg-rose-500/20 text-rose-300" : "bg-amber-500/15 text-amber-300"
                      )}
                    >
                      {a.type.replaceAll("_", " ")}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-zinc-500">{a.body}</p>
                  <div className="mt-2 text-[10px] uppercase tracking-wide text-zinc-600">
                    {new Date(a.created_at).toLocaleString()}
                  </div>
                </Link>
              </li>
            ))}
            {!live.length && !adminQ.isPending && (
              <li className="text-sm text-zinc-500">No live alerts — scrapes look healthy.</li>
            )}
          </ul>
        </section>

        <section className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="mb-4 flex items-center gap-2">
            <Bell size={16} className="text-[#ff4d00]" />
            <h2 className="text-sm font-semibold">Notification history</h2>
            <span className="text-xs text-zinc-500">{notifs.length}</span>
          </div>
          <ul className="space-y-2">
            {notifs.map((n) => (
              <li
                key={n.id}
                className={cn(
                  "rounded-xl border border-white/[0.04] bg-black/40 px-3 py-3",
                  n.is_read && "opacity-60"
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="text-sm font-medium">{n.title}</div>
                  {!n.is_read && <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-[#ff3b30]" />}
                </div>
                <p className="mt-1 text-xs text-zinc-500">{n.body}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wide text-zinc-600">
                  <span>{new Date(n.created_at).toLocaleString()}</span>
                  <span>·</span>
                  <span>{n.type.replaceAll("_", " ")}</span>
                  {n.profile_id && (
                    <>
                      <span>·</span>
                      <Link href={`/admin-scraping/${n.profile_id}`} className="text-[#ff3b30] hover:underline">
                        Open creator
                      </Link>
                    </>
                  )}
                </div>
              </li>
            ))}
            {!notifQ.isPending && !notifs.length && (
              <li className="text-sm text-zinc-500">
                You’ll see growth and scrape alerts here as scrapes run.
              </li>
            )}
          </ul>
        </section>
      </div>
    </div>
  );
}
