"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { SparkAdminProfilePoints } from "@/lib/spark/api-types";
import { formatNumber } from "@/lib/utils";
import { TaskHistoryTimeline } from "@/components/spark/task-history-timeline";

const BREAKDOWN_LABELS: Array<[string, string]> = [
  ["consistency", "Consistency"],
  ["performance", "Performance"],
  ["growth", "Growth"],
  ["bonus", "Manual bonus"],
  ["collaborations", "Collaborations"],
  ["revenue", "Revenue"],
  ["recognition", "Recognition"],
  ["participation", "Participation"],
  ["monthly_bonuses", "Monthly bonus"],
];

/**
 * Admin view of one student's points: the same full task history the student
 * sees, with the category breakdown. Query key sits under ["spark"], so adding
 * manual points (which invalidates ["spark"]) refreshes it.
 */
export function AdminPointsTimelineCard({ profileId }: { profileId: string }) {
  const q = useQuery({
    queryKey: ["spark", "admin", "profile-points", profileId],
    queryFn: () => api<SparkAdminProfilePoints>(`/spark/admin/profiles/${profileId}/points`),
    enabled: Boolean(profileId),
  });

  const data = q.data;
  const breakdown = BREAKDOWN_LABELS.filter(([key]) => (data?.points_breakdown?.[key] ?? 0) !== 0);

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Task history timeline</h2>
          <p className="mt-0.5 text-xs text-zinc-500">
            Every point this student has earned, newest first — exactly what they see on their dashboard.
            {data ? ` Programme window ${data.window_from} → ${data.window_to}.` : null}
          </p>
        </div>
        {data ? (
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-wide text-zinc-500">
              {data.rank ? `Rank #${data.rank} of ${data.ranked_total}` : "Not ranked yet"}
            </div>
            <div className="text-xl font-semibold tabular">{formatNumber(data.points)} pts</div>
          </div>
        ) : null}
      </div>

      {q.isLoading && <p className="mt-4 text-sm text-zinc-500">Loading points…</p>}
      {q.isError && (
        <p className="mt-4 text-sm text-rose-300">
          {(q.error as Error)?.message || "Could not load points"}
        </p>
      )}

      {data && breakdown.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {breakdown.map(([key, label]) => (
            <div key={key} className="rounded-xl border border-white/[0.06] bg-black/30 px-3 py-1.5">
              <div className="text-[10px] uppercase tracking-wide text-zinc-500">{label}</div>
              <div className="text-sm font-semibold tabular">
                {formatNumber(data.points_breakdown[key] ?? 0)}
              </div>
            </div>
          ))}
        </div>
      )}

      {data && (
        <div className="mt-5 border-t border-white/[0.06] pt-4">
          <TaskHistoryTimeline
            items={data.task_history}
            emptyText="No points yet — they appear once this student's posts are scraped."
          />
        </div>
      )}
    </div>
  );
}
