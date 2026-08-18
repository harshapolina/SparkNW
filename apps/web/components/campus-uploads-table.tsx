"use client";

import type { CampusUploadsBoard, CampusUploadsBreakdown } from "@/lib/spark/api-types";
import { formatNumber } from "@/lib/utils";

type Platform = "instagram" | "youtube" | "overall";

const HINT: Record<Platform, string> = {
  instagram: "All Instagram uploads (posts, reels, carousels) in the programme window.",
  youtube: "All YouTube uploads (videos + Shorts) in the programme window.",
  overall: "Instagram + YouTube uploads combined, by campus and month.",
};

const TITLE: Record<Platform, string> = {
  instagram: "Instagram uploads by campus",
  youtube: "YouTube uploads by campus",
  overall: "All uploads by campus",
};

export function CampusUploadsTable({
  data,
  platform,
  title,
}: {
  data?: CampusUploadsBreakdown | null;
  platform: Platform;
  title?: string;
}) {
  const months = data?.months || [];
  const board: CampusUploadsBoard | undefined = data?.[platform];
  const rows = board?.rows || [];

  return (
    <div className="overflow-hidden rounded-2xl border border-white/[0.06] bg-[#121212]">
      <div className="border-b border-white/[0.06] px-5 py-4">
        <h2 className="text-sm font-semibold">{title || TITLE[platform]}</h2>
        <p className="mt-0.5 text-xs text-zinc-500">{HINT[platform]} July is partial (from 15 Jul).</p>
      </div>
      {!months.length || !rows.length ? (
        <p className="px-5 py-8 text-sm text-zinc-500">No uploads in the programme window yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-[10px] uppercase tracking-[0.12em] text-zinc-500">
                <th className="px-5 py-2.5 font-medium">Campus</th>
                {months.map((m) => (
                  <th key={m.id} className="px-3 py-2.5 text-right font-medium tabular">
                    {m.label}
                  </th>
                ))}
                <th className="px-5 py-2.5 text-right font-medium tabular">Total</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.campus} className="border-b border-white/[0.04] last:border-0">
                  <td className="max-w-[220px] truncate px-5 py-2.5 text-zinc-200">{row.campus}</td>
                  {row.counts.map((n, i) => (
                    <td key={months[i]?.id || i} className="px-3 py-2.5 text-right tabular text-zinc-300">
                      {formatNumber(n)}
                    </td>
                  ))}
                  <td className="px-5 py-2.5 text-right font-semibold tabular">{formatNumber(row.total)}</td>
                </tr>
              ))}
            </tbody>
            {board ? (
              <tfoot>
                <tr className="border-t border-white/[0.08] text-zinc-100">
                  <td className="px-5 py-2.5 font-semibold">All campuses</td>
                  {board.totals.map((n, i) => (
                    <td key={months[i]?.id || i} className="px-3 py-2.5 text-right font-semibold tabular">
                      {formatNumber(n)}
                    </td>
                  ))}
                  <td className="px-5 py-2.5 text-right font-semibold tabular text-[#ff3b30]">
                    {formatNumber(board.grand_total)}
                  </td>
                </tr>
              </tfoot>
            ) : null}
          </table>
        </div>
      )}
    </div>
  );
}
