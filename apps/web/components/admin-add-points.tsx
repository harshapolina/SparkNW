"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { api, type Profile } from "@/lib/api";
import { formatNumber } from "@/lib/utils";

type BonusLogEntry = {
  points?: number;
  reason?: string;
  added_at?: string;
  added_by?: string;
  total_after?: number;
};

type AddBonusResponse = {
  bonus_points: number;
  added: number;
  log: BonusLogEntry[];
};

function bonusFromInsights(insights: Record<string, unknown> | undefined): number {
  const raw = insights?.spark_bonus_points;
  const n = typeof raw === "number" ? raw : Number(raw || 0);
  return Number.isFinite(n) ? n : 0;
}

function logFromInsights(insights: Record<string, unknown> | undefined): BonusLogEntry[] {
  const raw = insights?.spark_bonus_log;
  return Array.isArray(raw) ? (raw as BonusLogEntry[]) : [];
}

export function AdminAddPointsCard({
  profileId,
  insights,
}: {
  profileId: string;
  insights?: Record<string, unknown>;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [points, setPoints] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const current = bonusFromInsights(insights);
  const log = logFromInsights(insights);

  const add = useMutation({
    mutationFn: (payload: { points: number; reason: string }) =>
      api<AddBonusResponse>(`/spark/profiles/${profileId}/bonus-points`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: (data) => {
      setPoints("");
      setReason("");
      setError("");
      setOpen(false);
      qc.setQueryData<Profile>(["profile", profileId], (prev) => {
        if (!prev) return prev;
        const nextInsights = {
          ...(prev.insights || {}),
          spark_bonus_points: data.bonus_points,
          spark_bonus_log: data.log,
        };
        return { ...prev, insights: nextInsights };
      });
      void qc.invalidateQueries({ queryKey: ["profile", profileId] });
      void qc.invalidateQueries({ queryKey: ["spark"] });
      void qc.invalidateQueries({ queryKey: ["leaderboard"] });
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Could not add points");
    },
  });

  const submit = () => {
    const n = Number(points);
    if (!Number.isInteger(n) || n === 0) {
      setError("Enter a whole number (not 0)");
      return;
    }
    setError("");
    add.mutate({ points: n, reason: reason.trim() });
  };

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">SPARK points</h2>
          <p className="mt-0.5 text-xs text-zinc-500">
            Manual points added here update the leaderboard, student dashboard, and admin overview.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-wide text-zinc-500">Manual bonus</div>
            <div className="text-xl font-semibold tabular">{formatNumber(current)}</div>
          </div>
          <button
            type="button"
            onClick={() => {
              setOpen((v) => !v);
              setError("");
            }}
            className="inline-flex items-center gap-2 rounded-xl bg-[#ff3b30] px-4 py-2 text-sm font-semibold"
          >
            <Plus size={14} />
            Add
          </button>
        </div>
      </div>

      {open && (
        <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,140px)_1fr_auto] sm:items-end">
          <label className="block text-xs text-zinc-400">
            Points
            <input
              autoFocus
              type="number"
              step={1}
              value={points}
              onChange={(e) => setPoints(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
              }}
              placeholder="e.g. 50"
              className="mt-1 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white outline-none focus:border-[#ff3b30]/60"
            />
          </label>
          <label className="block text-xs text-zinc-400">
            Reason (optional)
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
              }}
              placeholder="Why these points?"
              maxLength={240}
              className="mt-1 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white outline-none focus:border-[#ff3b30]/60"
            />
          </label>
          <button
            type="button"
            disabled={add.isPending}
            onClick={submit}
            className="rounded-xl border border-white/10 bg-black/40 px-4 py-2 text-sm font-medium disabled:opacity-60"
          >
            {add.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      )}

      {error && <p className="mt-3 text-sm text-rose-300">{error}</p>}

      {log.length > 0 && (
        <ul className="mt-4 space-y-1.5 border-t border-white/[0.06] pt-3 text-xs text-zinc-500">
          {log.slice(0, 6).map((row, i) => (
            <li key={`${row.added_at || i}-${i}`} className="flex flex-wrap items-baseline gap-x-2">
              <span className={Number(row.points) >= 0 ? "font-medium tabular text-emerald-400" : "font-medium tabular text-rose-400"}>
                {Number(row.points) >= 0 ? "+" : ""}
                {formatNumber(Number(row.points || 0))}
              </span>
              {row.reason ? <span className="text-zinc-300">{row.reason}</span> : null}
              {row.added_at ? (
                <span>
                  {new Date(row.added_at).toLocaleString(undefined, {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
