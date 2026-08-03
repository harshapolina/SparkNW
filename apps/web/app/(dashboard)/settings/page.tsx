"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Bell, Check, Clock, Moon, Save, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
        checked ? "bg-stone-900" : "bg-stone-300"
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-soft transition",
          checked ? "left-[22px]" : "left-0.5"
        )}
      />
    </button>
  );
}

function applyDarkMode(on: boolean) {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", on);
  document.documentElement.dataset.theme = on ? "dark" : "light";
}

export default function SettingsPage() {
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
      applyDarkMode(data.dark_mode);
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
      if (
        Number.isNaN(payload.follower_growth_notify_pct!) ||
        payload.follower_growth_notify_pct! < 0
      ) {
        throw new Error("Follower growth % must be a number ≥ 0");
      }
      if (Number.isNaN(payload.engagement_spike_pct!) || payload.engagement_spike_pct! < 0) {
        throw new Error("Engagement spike % must be a number ≥ 0");
      }
      return api<Settings>("/settings", { method: "PATCH", body: JSON.stringify(payload) });
    },
    onSuccess: (saved) => {
      setDraft({});
      setMessage({ type: "ok", text: "Settings saved." });
      applyDarkMode(saved.dark_mode);
      qc.setQueryData(["settings"], saved);
    },
    onError: (e: Error) => {
      setMessage({ type: "err", text: e.message || "Could not save settings." });
    },
  });

  function setField<K extends keyof Settings>(key: K, v: Settings[K]) {
    setMessage(null);
    setDraft((d) => ({ ...d, [key]: v }));
    if (key === "dark_mode") applyDarkMode(Boolean(v));
  }

  if (isLoading) {
    return (
      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)] lg:min-h-[calc(100vh-140px)]">
        <div className="h-64 skeleton rounded-[22px]" />
        <div className="h-64 skeleton rounded-[22px]" />
      </div>
    );
  }

  if (loadError || !data) {
    return (
      <div className="rounded-[22px] bg-[#FFD9D2] px-5 py-4 text-sm text-[#9f1239]">
        {(loadError as Error)?.message || "Failed to load settings"}
      </div>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)] lg:items-stretch lg:min-h-[calc(100vh-140px)]">
      {/* Appearance / workspace */}
      <aside className="flex flex-col overflow-hidden rounded-[22px] bg-[#E9E0FF] shadow-card">
        <div className="border-b border-stone-900/5 px-5 py-4">
          <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-stone-500">Workspace</div>
          <div className="mt-1 font-[family-name:var(--font-display)] text-xl font-semibold tracking-tight">
            Settings
          </div>
          <p className="mt-1 text-xs leading-relaxed text-stone-600">
            Theme, timezone, and how alerts fire.
          </p>
        </div>

        <div className="flex flex-1 flex-col gap-3 p-4">
          <div className="rounded-2xl bg-white/75 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-stone-900 text-white">
                  <Moon size={15} />
                </div>
                <div>
                  <div className="text-sm font-semibold">Dark mode</div>
                  <p className="text-[11px] text-stone-500">Applies instantly, saves with the rest</p>
                </div>
              </div>
              <Toggle
                label="Dark mode"
                checked={Boolean(value.dark_mode)}
                onChange={(v) => setField("dark_mode", v)}
              />
            </div>
          </div>

          <div className="rounded-2xl bg-white/75 p-4">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sky-100 text-sky-700">
                <Clock size={15} />
              </div>
              <div>
                <div className="text-sm font-semibold">Timezone</div>
                <p className="text-[11px] text-stone-500">Used for daily growth windows</p>
              </div>
            </div>
            <select
              className="mt-3 h-11 w-full rounded-xl border border-stone-200/80 bg-white px-3.5 text-sm outline-none focus:border-stone-400"
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

          <div className="mt-auto rounded-2xl bg-white/50 px-3.5 py-3">
            <div className="flex items-start gap-2">
              <Sparkles size={14} className="mt-0.5 text-stone-500" />
              <p className="text-xs leading-relaxed text-stone-600">
                Alert thresholds use your last scrape snapshot. Save before leaving if the button is active.
              </p>
            </div>
          </div>
        </div>
      </aside>

      {/* Alerts */}
      <section className="flex flex-col overflow-hidden rounded-[22px] bg-white shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-200/70 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#FFE8D6] text-[#c2410c]">
              <Bell size={15} />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight">Alerts</div>
              <p className="text-xs text-stone-500">Thresholds and which events create notifications</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {dirty && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setDraft({});
                  setMessage(null);
                  applyDarkMode(data.dark_mode);
                }}
              >
                Discard
              </Button>
            )}
            <Button
              onClick={() => save.mutate()}
              disabled={save.isPending || !dirty}
              className="min-w-[130px]"
            >
              {save.isPending ? (
                "Saving…"
              ) : (
                <>
                  <Save size={15} />
                  Save changes
                </>
              )}
            </Button>
          </div>
        </div>

        {message && (
          <div
            className={cn(
              "mx-5 mt-4 flex items-center gap-2 rounded-xl px-3.5 py-2.5 text-sm",
              message.type === "ok" ? "bg-[#d1fae5] text-[#047857]" : "bg-[#FFD9D2] text-[#9f1239]"
            )}
          >
            {message.type === "ok" && <Check size={14} />}
            {message.text}
          </div>
        )}

        <div className="grid flex-1 gap-4 p-5 md:grid-cols-2">
          <div className="rounded-2xl bg-[#f3efe8] p-4">
            <label className="text-sm font-semibold text-stone-900">Follower growth notify %</label>
            <p className="mt-1 text-xs text-stone-500">Alert when daily growth exceeds this.</p>
            <Input
              className="mt-3"
              type="number"
              min={0}
              step={0.1}
              value={value.follower_growth_notify_pct}
              onChange={(e) => setField("follower_growth_notify_pct", Number(e.target.value))}
            />
          </div>

          <div className="rounded-2xl bg-[#f3efe8] p-4">
            <label className="text-sm font-semibold text-stone-900">Engagement spike %</label>
            <p className="mt-1 text-xs text-stone-500">Alert when engagement jumps vs last scrape.</p>
            <Input
              className="mt-3"
              type="number"
              min={0}
              step={1}
              value={value.engagement_spike_pct}
              onChange={(e) => setField("engagement_spike_pct", Number(e.target.value))}
            />
          </div>

          <div className="space-y-1 rounded-2xl border border-stone-200/70 p-2 md:col-span-2">
            {(
              [
                ["notify_followers_down", "Notify on follower drop", "When followers fall vs previous scrape"],
                ["notify_scrape_failed", "Notify on scrape failure", "When a profile refresh fails"],
                ["notify_engagement_spike", "Notify on engagement spike", "When engagement crosses your spike %"],
              ] as const
            ).map(([key, label, hint]) => (
              <div
                key={key}
                className="flex items-center justify-between gap-4 rounded-xl px-3 py-3 hover:bg-stone-50"
              >
                <div>
                  <div className="text-sm font-medium text-stone-900">{label}</div>
                  <div className="text-xs text-stone-500">{hint}</div>
                </div>
                <Toggle
                  label={label}
                  checked={Boolean(value[key])}
                  onChange={(v) => setField(key, v)}
                />
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-stone-200/70 px-5 py-3 text-xs text-stone-500">
          {dirty ? "You have unsaved changes." : "All changes saved."}
        </div>
      </section>
    </div>
  );
}
