import type { SparkTaskHistoryItem } from "@/lib/spark/api-types";

function dotClass(status: string): string {
  if (status === "approved") return "bg-lime-400";
  if (status === "missed") return "bg-rose-500";
  if (status === "capped") return "bg-amber-400";
  return "bg-zinc-600";
}

function pointsLabel(points: number): string {
  if (points > 0) return `+${points} pts`;
  if (points < 0) return `−${Math.abs(points)} pts`;
  return "0 pts";
}

function itemHref(t: SparkTaskHistoryItem): string | null {
  if (t.url) return t.url;
  if (t.shortcode) return `https://www.instagram.com/p/${t.shortcode}/`;
  return null;
}

/**
 * Where each SPARK point came from — the full list, newest first.
 * Shared by the student dashboard and the admin student page so both show the
 * same thing. Entries sum to the student's total (cap and balance lines included).
 */
export function TaskHistoryTimeline({
  items,
  emptyText = "Refresh the profile to earn performance points from posts.",
}: {
  items: SparkTaskHistoryItem[];
  emptyText?: string;
}) {
  if (!items.length) return <p className="text-sm text-zinc-500">{emptyText}</p>;

  return (
    <div className="space-y-0">
      {items.map((t, i) => {
        const href = itemHref(t);
        return (
          <div key={t.id} className="relative flex gap-4 pb-5 last:pb-0">
            <div className="flex flex-col items-center">
              <div className={`mt-1 h-2.5 w-2.5 rounded-full ${dotClass(t.status)}`} />
              {i < items.length - 1 && <div className="w-px flex-1 bg-white/10" />}
            </div>
            <div className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="break-words text-sm font-medium">{t.title}</div>
                <div className="text-[11px] text-zinc-500">
                  {t.category} · {t.date}
                  {href ? (
                    <>
                      {" · "}
                      <a
                        href={href}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[#ff4d00] hover:underline"
                      >
                        open
                      </a>
                    </>
                  ) : null}
                </div>
              </div>
              <div
                className={`shrink-0 text-sm font-semibold tabular ${
                  t.points < 0 ? "text-zinc-400" : "text-[#ff4d00]"
                }`}
              >
                {pointsLabel(t.points)}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
