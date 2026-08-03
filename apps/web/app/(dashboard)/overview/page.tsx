"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Eye,
  Heart,
  MoreHorizontal,
  TrendingUp,
  Users,
  BadgeCheck,
} from "lucide-react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { api, type Profile } from "@/lib/api";
import { formatNumber, formatPct } from "@/lib/utils";
import { Avatar } from "@/components/ui/avatar";

type Overview = {
  stats: {
    total_profiles: number;
    profiles_updated_today: number;
    failed_updates: number;
    average_engagement: number;
    average_followers: number;
    average_views: number;
    average_likes: number;
    follower_growth_today: number;
  };
  charts: {
    followers_over_time: { date: string; value: number }[];
    posts_per_day: { date: string; value: number }[];
    content_types: { name: string; value: number }[];
  };
  recent_updates: Profile[];
};

const PASTELS = [
  { bg: "#FFE8D6", icon: "bg-white/70 text-[#c2410c]", tip: "badge-orange" },
  { bg: "#D9EEFF", icon: "bg-white/70 text-[#0369a1]", tip: "badge-blue" },
  { bg: "#E9E0FF", icon: "bg-white/70 text-[#6d28d9]", tip: "badge-purple" },
  { bg: "#FFD9D2", icon: "bg-white/70 text-[#be123c]", tip: "badge-pink" },
  { bg: "#F8D7E8", icon: "bg-white/70 text-[#be185d]", tip: "badge-pink" },
  { bg: "#E4D4F4", icon: "bg-white/70 text-[#7c3aed]", tip: "badge-purple" },
];

function MiniTip({ active, payload }: { active?: boolean; payload?: { value: number }[] }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl bg-white px-2.5 py-1.5 text-xs shadow-card">
      {formatNumber(payload[0].value)}
    </div>
  );
}

export default function OverviewPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["overview"],
    queryFn: () => api<Overview>("/analytics/overview"),
  });

  const profiles = data?.recent_updates || [];
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selected = useMemo(() => {
    if (!profiles.length) return null;
    return profiles.find((p) => p.id === selectedId) || profiles[0];
  }, [profiles, selectedId]);

  const topProfiles = useMemo(() => {
    return [...profiles]
      .sort((a, b) => Math.abs(b.growth_pct_today) - Math.abs(a.growth_pct_today))
      .slice(0, 4);
  }, [profiles]);

  if (isLoading) {
    return (
      <div className="space-y-5">
        <div className="h-10 w-64 skeleton" />
        <div className="grid gap-4 md:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-36 skeleton" />)}</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-[22px] bg-[#FFD9D2] px-5 py-4 text-sm text-[#9f1239]">
        {(error as Error)?.message || "Failed to load overview"}
      </div>
    );
  }

  const s = data.stats;
  const metrics = [
    { label: "Total Profiles", value: formatNumber(s.total_profiles), hint: "Accounts tracked", icon: Users, delta: `${s.profiles_updated_today} updated today` },
    { label: "Updated Today", value: formatNumber(s.profiles_updated_today), hint: "Fresh scrapes", icon: Activity, delta: "Live cadence" },
    { label: "Failed Updates", value: formatNumber(s.failed_updates), hint: "Needs attention", icon: AlertTriangle, delta: s.failed_updates ? "Review alerts" : "All healthy" },
    { label: "Avg Engagement", value: `${s.average_engagement.toFixed(2)}%`, hint: "Likes + comments / followers", icon: TrendingUp, delta: "Portfolio avg" },
    { label: "Avg Followers", value: formatNumber(s.average_followers), hint: "Across tracked profiles", icon: Users, delta: formatPct(0) },
    { label: "Avg Likes", value: formatNumber(s.average_likes), hint: "From recent posts", icon: Heart, delta: `Views ${formatNumber(s.average_views)}` },
  ];

  const contentTotal = data.charts.content_types.reduce((a, b) => a + b.value, 0) || 1;
  const contentBars = data.charts.content_types.slice(0, 3).map((c, i) => ({
    ...c,
    pct: Math.round((c.value / contentTotal) * 100),
    color: i === 0 ? "bg-[#a78bfa]" : i === 1 ? "bg-[#f9a8d4]" : "bg-[#7dd3fc]",
  }));

  return (
    <div className="space-y-6">
      {/* Header + Top Profiles */}
      <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 className="page-title">Profile Intelligence</h1>
          <p className="mt-1 text-sm text-stone-500">Live Instagram monitoring across your portfolio</p>
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-2 xl:max-w-3xl xl:items-end">
          <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-stone-400 xl:self-end">
            Top profiles
          </div>
          <div className="flex gap-3 overflow-x-auto pb-1">
            {topProfiles.map((p, idx) => (
              <button
                key={p.id}
                onClick={() => setSelectedId(p.id)}
                className={`flex min-w-[200px] items-center gap-3 rounded-[20px] bg-white px-3 py-2.5 text-left shadow-card transition hover:-translate-y-0.5 ${
                  selected?.id === p.id ? "ring-2 ring-stone-900/10" : ""
                }`}
              >
                <Avatar name={p.username} size="md" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold">@{p.username}</div>
                  <div className="truncate text-[11px] text-stone-400">{p.full_name || "Tracked profile"}</div>
                </div>
                <span className={idx % 2 === 0 ? "badge-pink" : "badge-purple"}>
                  {formatPct(p.growth_pct_today)}
                </span>
              </button>
            ))}
            {!topProfiles.length && (
              <Link href="/profiles" className="rounded-[20px] bg-white px-4 py-3 text-sm text-stone-500 shadow-card">
                Add profiles to see tops →
              </Link>
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_320px]">
        {/* Main column */}
        <div className="space-y-5">
          {/* Pastel metric cards */}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {metrics.map((m, i) => {
              const tone = PASTELS[i % PASTELS.length];
              const Icon = m.icon;
              return (
                <div
                  key={m.label}
                  className="pastel-card"
                  style={{ background: tone.bg }}
                >
                  <div className="flex items-start justify-between">
                    <div className={`flex h-9 w-9 items-center justify-center rounded-2xl ${tone.icon}`}>
                      <Icon size={16} />
                    </div>
                    <button className="rounded-full p-1 text-stone-400/80 hover:bg-white/40">
                      <MoreHorizontal size={16} />
                    </button>
                  </div>
                  <div className="mt-5 text-sm font-medium text-stone-600">{m.label}</div>
                  <div className="stat-value mt-1">{m.value}</div>
                  <div className="mt-3 text-[12px] text-stone-500">{m.delta}</div>
                </div>
              );
            })}
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            {/* Content / growth variance style */}
            <div className="soft-card p-5 md:p-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-base font-semibold tracking-tight">Content performance</div>
                  <div className="mt-0.5 text-xs text-stone-400">Mix across recent scraped posts</div>
                </div>
                <Link href="/analytics" className="text-xs font-medium text-stone-500 hover:text-stone-800">
                  Details
                </Link>
              </div>

              <div className="mt-6 space-y-5">
                {contentBars.length ? contentBars.map((bar) => (
                  <div key={bar.name}>
                    <div className="mb-2 flex items-center justify-between text-sm">
                      <span className="font-medium capitalize">{bar.name}</span>
                      <span className="tabular text-stone-500">{bar.pct}%</span>
                    </div>
                    <div className="h-2.5 overflow-hidden rounded-full bg-stone-100">
                      <div className={`h-full rounded-full ${bar.color}`} style={{ width: `${bar.pct}%` }} />
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-2 text-[11px] text-stone-400">
                      <div>Count <span className="font-medium text-stone-600">{bar.value}</span></div>
                      <div>Share <span className="font-medium text-stone-600">{bar.pct}%</span></div>
                      <div>Status <span className="font-medium text-stone-600">Tracked</span></div>
                    </div>
                  </div>
                )) : (
                  <p className="text-sm text-stone-400">Refresh profiles to populate content mix.</p>
                )}
              </div>

              <div className="mt-6 rounded-[18px] bg-[#f7f3ee] px-4 py-3">
                <div className="text-xs text-stone-400">Follower growth today</div>
                <div className="mt-1 font-[family-name:var(--font-display)] text-xl font-semibold tabular">
                  {formatNumber(s.follower_growth_today)}
                </div>
              </div>
            </div>

            {/* Milestones / activity */}
            <div className="soft-card p-5 md:p-6">
              <div className="text-base font-semibold tracking-tight">Monitoring activity</div>
              <div className="mt-0.5 text-xs text-stone-400">Latest scrapes and profile health</div>

              <div className="mt-5">
                <div className="mb-2 flex items-center justify-between text-xs">
                  <span className="text-stone-500">Freshness today</span>
                  <span className="font-medium">
                    {s.total_profiles ? Math.round((s.profiles_updated_today / s.total_profiles) * 100) : 0}%
                  </span>
                </div>
                <div className="h-3 overflow-hidden rounded-full bg-stone-100">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-[#c4b5fd] via-[#f9a8d4] to-[#fda4af]"
                    style={{
                      width: `${s.total_profiles ? Math.min(100, Math.round((s.profiles_updated_today / s.total_profiles) * 100)) : 0}%`,
                    }}
                  />
                </div>
              </div>

              <div className="mt-5 space-y-3">
                {profiles.slice(0, 4).map((p, i) => (
                  <button
                    key={p.id}
                    onClick={() => setSelectedId(p.id)}
                    className="flex w-full items-center gap-3 rounded-[16px] bg-[#f7f3ee] px-3 py-2.5 text-left transition hover:bg-[#efeae2]"
                  >
                    <Avatar name={p.username} size="md" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">@{p.username}</div>
                      <div className="text-[11px] text-stone-400">
                        {p.last_scraped_at ? new Date(p.last_scraped_at).toLocaleString() : "Not scraped yet"}
                      </div>
                    </div>
                    <span className={i % 3 === 0 ? "badge-blue" : i % 3 === 1 ? "badge-orange" : "badge-pink"}>
                      {p.status}
                    </span>
                  </button>
                ))}
                {!profiles.length && (
                  <p className="text-sm text-stone-400">No activity yet. Import or add a profile.</p>
                )}
              </div>
            </div>
          </div>

          {/* Followers sparkline card */}
          <div className="soft-card p-5 md:p-6">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="text-base font-semibold tracking-tight">Followers over time</div>
                <div className="text-xs text-stone-400">Portfolio average from daily snapshots</div>
              </div>
              <Link href="/profiles" className="inline-flex items-center gap-1 text-sm font-medium text-stone-600 hover:text-stone-900">
                View profiles <ArrowUpRight size={14} />
              </Link>
            </div>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.charts.followers_over_time}>
                  <defs>
                    <linearGradient id="creamFollowers" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#a78bfa" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <Tooltip content={<MiniTip />} />
                  <Area type="monotone" dataKey="value" stroke="#8b5cf6" fill="url(#creamFollowers)" strokeWidth={2.5} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Right detail panel */}
        <aside className="space-y-4">
          <div className="soft-card overflow-hidden">
            {selected ? (
              <>
                <div className="bg-gradient-to-br from-[#ede9fe] via-[#fce7f3] to-[#ffedd5] px-6 pb-10 pt-8 text-center">
                  <Avatar name={selected.username} size="xl" className="mx-auto ring-4 ring-white shadow-card" />
                  <div className="mt-4 flex items-center justify-center gap-1.5">
                    <h2 className="font-[family-name:var(--font-display)] text-lg font-semibold">@{selected.username}</h2>
                    {selected.is_verified && <BadgeCheck size={16} className="text-[#7c3aed]" />}
                  </div>
                  <p className="mt-1 text-sm text-stone-500">{selected.full_name || "Instagram profile"}</p>
                </div>

                <div className="-mt-5 px-4">
                  <div className="flex justify-center gap-2 rounded-[18px] bg-stone-100/90 p-2 shadow-soft">
                    <Link href={`/profiles/${selected.id}`} className="rounded-xl bg-white px-3 py-2 text-xs font-medium shadow-soft">
                      Open
                    </Link>
                    <div className="rounded-xl px-3 py-2 text-xs text-stone-500">{formatPct(selected.growth_pct_today)} growth</div>
                    <div className="rounded-xl px-3 py-2 text-xs capitalize text-stone-500">{selected.status}</div>
                  </div>
                </div>

                <div className="space-y-4 px-5 py-5">
                  <div className="text-sm font-semibold">Detailed information</div>
                  {[
                    ["Followers", formatNumber(selected.followers)],
                    ["Following", formatNumber(selected.following)],
                    ["Posts", formatNumber(selected.posts_count)],
                    ["Avg likes", formatNumber(selected.avg_likes)],
                    ["Avg views", formatNumber(selected.avg_views)],
                    ["Engagement", `${selected.engagement_rate.toFixed(2)}%`],
                    ["Last scraped", selected.last_scraped_at ? new Date(selected.last_scraped_at).toLocaleString() : "—"],
                  ].map(([label, value]) => (
                    <div key={label} className="flex items-center justify-between gap-3 border-b border-stone-100 pb-3 last:border-0">
                      <div className="flex items-center gap-2.5 text-sm text-stone-500">
                        <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#f7f3ee] text-stone-400">
                          {label === "Avg likes" ? <Heart size={13} /> : label === "Avg views" ? <Eye size={13} /> : <Users size={13} />}
                        </span>
                        {label}
                      </div>
                      <div className="text-sm font-semibold tabular text-stone-800">{value}</div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="p-8 text-center text-sm text-stone-400">
                Add a profile to see details here.
              </div>
            )}
          </div>

          <Link
            href="/imports"
            className="block rounded-[22px] bg-[#1c1917] px-5 py-4 text-white shadow-card transition hover:brightness-110"
          >
            <div className="text-sm font-semibold">Import from sheets</div>
            <div className="mt-1 text-xs text-stone-400">CSV, Excel, or Google Sheets → Import all</div>
          </Link>
        </aside>
      </div>
    </div>
  );
}
