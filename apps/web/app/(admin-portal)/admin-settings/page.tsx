"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Bell, Clock, Moon, Save, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Settings = {
  dark_mode: boolean;
  follower_growth_notify_pct: number;
  notify_followers_down: boolean;
  notify_scrape_failed: boolean;
  notify_engagement_spike: boolean;
  engagement_spike_pct: number;
  timezone: string;
};

const TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Asia/Kolkata",
  "Asia/Dubai",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
];

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-6 w-11 shrink-0 rounded-full transition",
        checked ? "bg-[#ff3b30]" : "bg-zinc-700"
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition",
          checked ? "left-[22px]" : "left-0.5"
        )}
      />
    </button>
  );
}

export default function AdminSettingsPage() {
  const qc = useQueryClient();
  const { data, isLoading, error: loadError } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Settings>("/settings"),
  });
  const [draft, setDraft] = useState<Partial<Settings>>({});
  const [message, setMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const value = useMemo(() => ({ ...(data || ({} as Settings)), ...draft }), [data, draft]);
  const dirty = Object.keys(draft).length > 0;

  useEffect(() => {
    if (data && typeof data.dark_mode === "boolean" && draft.dark_mode === undefined) {
      document.documentElement.classList.toggle("dark", data.dark_mode);
    }
  }, [data, draft.dark_mode]);

  const save = useMutation({
    mutationFn: async () => {
      const payload: Partial<Settings> = {
        dark_mode: value.dark_mode,
        follower_growth_notify_pct: Number(value.follower_growth_notify_pct),
        notify_followers_down: value.notify_followers_down,
        notify_scrape_failed: value.notify_scrape_failed,
        notify_engagement_spike: value.notify_engagement_spike,
        engagement_spike_pct: Number(value.engagement_spike_pct),
        timezone: value.timezone || "UTC",
      };
      if (Number.isNaN(payload.follower_growth_notify_pct!) || payload.follower_growth_notify_pct! < 0) {
        throw new Error("Follower growth % must be ≥ 0");
      }
      if (Number.isNaN(payload.engagement_spike_pct!) || payload.engagement_spike_pct! < 0) {
        throw new Error("Engagement spike % must be ≥ 0");
      }
      return api<Settings>("/settings", { method: "PATCH", body: JSON.stringify(payload) });
    },
    onSuccess: (saved) => {
      setDraft({});
      setMessage({ type: "ok", text: "Settings saved." });
      document.documentElement.classList.toggle("dark", saved.dark_mode);
      qc.setQueryData(["settings"], saved);
    },
    onError: (e: Error) => setMessage({ type: "err", text: e.message || "Could not save." }),
  });

  function setField<K extends keyof Settings>(key: K, v: Settings[K]) {
    setMessage(null);
    setDraft((d) => ({ ...d, [key]: v }));
    if (key === "dark_mode") document.documentElement.classList.toggle("dark", Boolean(v));
  }

  if (isLoading) return <div className="h-64 animate-pulse rounded-2xl bg-zinc-900" />;
  if (loadError || !data) {
    return (
      <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
        {(loadError as Error)?.message || "Failed to load settings"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link href="/admin-dashboard" className="text-xs text-zinc-500 hover:text-zinc-300">
            ← Dashboard
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">Settings</h1>
          <p className="mt-1 text-sm text-zinc-500">Theme, timezone, and how scrape/growth alerts fire.</p>
        </div>
        <button
          type="button"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate()}
          className="inline-flex items-center gap-2 rounded-xl bg-[#ff3b30] px-4 py-2 text-sm font-semibold disabled:opacity-50"
        >
          <Save size={14} />
          {save.isPending ? "Saving…" : "Save settings"}
        </button>
      </div>

      {message && (
        <div
          className={cn(
            "rounded-xl px-4 py-3 text-sm",
            message.type === "ok" ? "bg-emerald-500/10 text-emerald-300" : "bg-rose-500/10 text-rose-300"
          )}
        >
          {message.text}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="space-y-3 rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Moon size={16} className="text-[#ff4d00]" /> Workspace
          </div>
          <div className="flex items-center justify-between rounded-xl bg-black/40 px-4 py-3">
            <div>
              <div className="text-sm font-medium">Dark mode</div>
              <p className="text-[11px] text-zinc-500">Applies instantly, saves with the rest</p>
            </div>
            <Toggle label="Dark mode" checked={Boolean(value.dark_mode)} onChange={(v) => setField("dark_mode", v)} />
          </div>
          <div className="rounded-xl bg-black/40 px-4 py-3">
            <div className="flex items-center gap-2">
              <Clock size={14} className="text-sky-400" />
              <div className="text-sm font-medium">Timezone</div>
            </div>
            <p className="mt-1 text-[11px] text-zinc-500">Used for daily growth windows</p>
            <select
              className="mt-3 h-11 w-full rounded-xl border border-white/10 bg-black px-3 text-sm outline-none"
              value={value.timezone || "UTC"}
              onChange={(e) => setField("timezone", e.target.value)}
            >
              {!TIMEZONES.includes(value.timezone || "") && value.timezone && (
                <option value={value.timezone}>{value.timezone}</option>
              )}
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-start gap-2 rounded-xl bg-black/30 px-3 py-3 text-xs text-zinc-500">
            <Sparkles size={14} className="mt-0.5 shrink-0" />
            Alert thresholds use your last scrape snapshot. Save before leaving if the button is active.
          </div>
        </section>

        <section className="space-y-3 rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Bell size={16} className="text-[#ff3b30]" /> Alert thresholds
          </div>
          <label className="block rounded-xl bg-black/40 px-4 py-3">
            <div className="text-sm font-medium">Follower growth notify %</div>
            <p className="text-[11px] text-zinc-500">Notify when growth ≥ this %</p>
            <input
              type="number"
              min={0}
              step={0.1}
              className="mt-2 h-10 w-full rounded-lg border border-white/10 bg-black px-3 text-sm"
              value={value.follower_growth_notify_pct ?? 0}
              onChange={(e) => setField("follower_growth_notify_pct", Number(e.target.value))}
            />
          </label>
          <label className="block rounded-xl bg-black/40 px-4 py-3">
            <div className="text-sm font-medium">Engagement spike %</div>
            <input
              type="number"
              min={0}
              step={0.1}
              className="mt-2 h-10 w-full rounded-lg border border-white/10 bg-black px-3 text-sm"
              value={value.engagement_spike_pct ?? 0}
              onChange={(e) => setField("engagement_spike_pct", Number(e.target.value))}
            />
          </label>
          {[
            ["notify_followers_down", "Notify on followers down"],
            ["notify_scrape_failed", "Notify on scrape failure"],
            ["notify_engagement_spike", "Notify on engagement spike"],
          ].map(([key, label]) => (
            <div key={key} className="flex items-center justify-between rounded-xl bg-black/40 px-4 py-3">
              <div className="text-sm">{label}</div>
              <Toggle
                label={label}
                checked={Boolean(value[key as keyof Settings])}
                onChange={(v) => setField(key as keyof Settings, v as never)}
              />
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
