"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bell,
  Fingerprint,
  Gauge,
  Search,
  ShieldAlert,
  Siren,
  TrendingUp,
  Wrench,
} from "lucide-react";
import { api } from "@/lib/api";
import type { AdminAlert, AdminOverviewResponse } from "@/lib/spark/api-types";
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

type TabId =
  | "all"
  | "growth_anomaly"
  | "engagement_review"
  | "authenticity"
  | "bot_integrity"
  | "operations"
  | "inbox";

const TABS: {
  id: TabId;
  label: string;
  hint: string;
  icon: typeof Siren;
  accent: string;
}[] = [
  { id: "all", label: "All live", hint: "Every open integrity + ops flag", icon: Bell, accent: "text-zinc-200" },
  {
    id: "growth_anomaly",
    label: "Growth spikes",
    hint: "+3,000 followers or large view jumps in 48h → manual audit",
    icon: TrendingUp,
    accent: "text-amber-300",
  },
  {
    id: "engagement_review",
    label: "Engagement",
    hint: "<1% engagement at 10K+ followers",
    icon: Gauge,
    accent: "text-sky-300",
  },
  {
    id: "authenticity",
    label: "Authenticity",
    hint: "Verify at 10K / 30K / 50K (Modash, HypeAuditor)",
    icon: Fingerprint,
    accent: "text-violet-300",
  },
  {
    id: "bot_integrity",
    label: "Bot integrity",
    hint: "First hit −500 pts + warning · second = DQ",
    icon: ShieldAlert,
    accent: "text-rose-300",
  },
  {
    id: "operations",
    label: "Scrape ops",
    hint: "Failed scrapes and private accounts",
    icon: Wrench,
    accent: "text-zinc-300",
  },
  { id: "inbox", label: "Inbox", hint: "Stored notification history", icon: Bell, accent: "text-orange-300" },
];

function categoryOf(a: AdminAlert): Exclude<TabId, "all" | "inbox"> {
  const c = a.category;
  if (
    c === "growth_anomaly" ||
    c === "engagement_review" ||
    c === "authenticity" ||
    c === "bot_integrity" ||
    c === "operations"
  ) {
    return c;
  }
  if (a.type === "scrape_failed" || a.type === "profile_private") return "operations";
  if (a.type.includes("engagement")) return "engagement_review";
  return "growth_anomaly";
}

function severityClass(sev: string) {
  if (sev === "critical") return "bg-rose-500/20 text-rose-200 ring-1 ring-rose-500/40";
  if (sev === "high") return "bg-amber-500/15 text-amber-200 ring-1 ring-amber-500/30";
  return "bg-white/5 text-zinc-400 ring-1 ring-white/10";
}

function AlertCard({ a }: { a: AdminAlert }) {
  return (
    <Link
      href={`/admin-scraping/${a.profile_id}`}
      className="group block rounded-2xl border border-white/[0.06] bg-gradient-to-br from-white/[0.04] to-transparent p-4 transition hover:border-[#ff3b30]/35 hover:from-[#ff3b30]/10"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-medium text-zinc-500">@{a.username}</div>
          <h3 className="mt-0.5 text-sm font-semibold tracking-tight text-zinc-100 group-hover:text-white">
            {a.title}
          </h3>
        </div>
        <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase", severityClass(a.severity))}>
          {a.severity}
        </span>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-zinc-400">{a.body}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-zinc-600">
        <span>{new Date(a.created_at).toLocaleString()}</span>
        <span className="text-zinc-700">·</span>
        <span>{a.type.replaceAll("_", " ")}</span>
        {typeof a.followers === "number" ? (
          <>
            <span className="text-zinc-700">·</span>
            <span>{a.followers.toLocaleString()} followers</span>
          </>
        ) : null}
        {a.action ? (
          <>
            <span className="text-zinc-700">·</span>
            <span className="text-[#ff8a80]">{a.action.replaceAll("_", " ")}</span>
          </>
        ) : null}
      </div>
    </Link>
  );
}

export default function AdminAlertsPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabId>("all");
  const [q, setQ] = useState("");

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
  const unread = notifs.filter((n) => !n.is_read).length;

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: live.length, inbox: notifs.length };
    for (const a of live) {
      const cat = categoryOf(a);
      c[cat] = (c[cat] || 0) + 1;
    }
    return c;
  }, [live, notifs.length]);

  const filteredLive = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return live.filter((a) => {
      if (tab !== "all" && tab !== "inbox" && categoryOf(a) !== tab) return false;
      if (!needle) return true;
      return `${a.title} ${a.body} ${a.username} ${a.type}`.toLowerCase().includes(needle);
    });
  }, [live, tab, q]);

  const filteredInbox = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return notifs;
    return notifs.filter((n) => `${n.title} ${n.body} ${n.type}`.toLowerCase().includes(needle));
  }, [notifs, q]);

  const showingInbox = tab === "inbox";
  const activeHint = TABS.find((t) => t.id === tab)?.hint;

  return (
    <div className="relative space-y-6">
      <div className="pointer-events-none absolute -left-10 -top-16 h-56 w-56 rounded-full bg-[#ff3b30]/10 blur-3xl" />
      <div className="pointer-events-none absolute right-0 top-0 h-40 w-40 rounded-full bg-violet-600/10 blur-3xl" />

      <div className="relative flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#ff3b30]">Integrity desk</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Alerts</h1>
          <p className="mt-1 max-w-xl text-sm text-zinc-500">
            Anti-gaming controls, scrape health, and inbox — split by rule so nothing sits in one mixed pile.
          </p>
        </div>
        <button
          type="button"
          disabled={markAll.isPending || !unread}
          onClick={() => markAll.mutate()}
          className="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-zinc-200 hover:border-[#ff3b30]/40 disabled:opacity-40"
        >
          Mark inbox read{unread ? ` (${unread})` : ""}
        </button>
      </div>

      <div className="relative grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Manual audits", value: counts.growth_anomaly || 0, icon: Siren, tone: "text-amber-300" },
          { label: "Engagement reviews", value: counts.engagement_review || 0, icon: Gauge, tone: "text-sky-300" },
          { label: "Authenticity checks", value: counts.authenticity || 0, icon: Fingerprint, tone: "text-violet-300" },
          { label: "Bot flags", value: counts.bot_integrity || 0, icon: ShieldAlert, tone: "text-rose-300" },
        ].map((s) => (
          <div
            key={s.label}
            className="rounded-2xl border border-white/[0.06] bg-[#121212]/80 px-4 py-3 backdrop-blur"
          >
            <div className="flex items-center justify-between">
              <span className="text-[11px] uppercase tracking-[0.14em] text-zinc-500">{s.label}</span>
              <s.icon size={14} className={s.tone} />
            </div>
            <div className="mt-2 text-2xl font-semibold tabular tracking-tight">{s.value}</div>
          </div>
        ))}
      </div>

      <div className="relative flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex max-w-full gap-1 overflow-x-auto pb-1">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            const n = t.id === "all" ? live.length : t.id === "inbox" ? notifs.length : counts[t.id] || 0;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={cn(
                  "inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition",
                  active
                    ? "bg-white text-black shadow-[0_0_24px_rgba(255,59,48,0.18)]"
                    : "bg-white/[0.04] text-zinc-400 hover:bg-white/[0.08] hover:text-zinc-200"
                )}
              >
                <Icon size={12} className={active ? "text-[#ff3b30]" : t.accent} />
                {t.label}
                <span className={cn("tabular", active ? "text-zinc-500" : "text-zinc-600")}>{n}</span>
              </button>
            );
          })}
        </div>
        <label className="relative w-full max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search handle, rule, body…"
            className="w-full rounded-full border border-white/10 bg-black/50 py-2 pl-9 pr-3 text-sm outline-none focus:border-[#ff3b30]/50"
          />
        </label>
      </div>

      <p className="relative text-xs text-zinc-500">{activeHint}</p>

      {showingInbox ? (
        <ul className="relative space-y-2">
          {filteredInbox.map((n) => (
            <li
              key={n.id}
              className={cn(
                "rounded-2xl border border-white/[0.06] bg-[#121212] px-4 py-3",
                n.is_read && "opacity-55"
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="text-sm font-medium">{n.title}</div>
                {!n.is_read && <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-[#ff3b30] shadow-[0_0_10px_#ff3b30]" />}
              </div>
              <p className="mt-1 text-xs text-zinc-500">{n.body}</p>
              <div className="mt-2 flex flex-wrap gap-2 text-[10px] uppercase tracking-wide text-zinc-600">
                <span>{new Date(n.created_at).toLocaleString()}</span>
                <span>{n.type.replaceAll("_", " ")}</span>
                {n.profile_id && (
                  <Link href={`/admin-scraping/${n.profile_id}`} className="text-[#ff3b30] hover:underline">
                    Open creator
                  </Link>
                )}
              </div>
            </li>
          ))}
          {!notifQ.isPending && !filteredInbox.length && (
            <li className="rounded-2xl border border-dashed border-white/10 px-6 py-12 text-center text-sm text-zinc-500">
              Inbox is clear.
            </li>
          )}
        </ul>
      ) : (
        <ul className="relative grid gap-3 lg:grid-cols-2">
          {filteredLive.map((a) => (
            <li key={a.id}>
              <AlertCard a={a} />
            </li>
          ))}
          {!adminQ.isPending && !filteredLive.length && (
            <li className="col-span-full rounded-2xl border border-dashed border-white/10 px-6 py-16 text-center">
              <AlertTriangle size={18} className="mx-auto text-zinc-600" />
              <p className="mt-3 text-sm text-zinc-400">Nothing in this lane right now.</p>
              <p className="mt-1 text-xs text-zinc-600">Spikes, low engagement, and milestone checks appear as scrapes land.</p>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
