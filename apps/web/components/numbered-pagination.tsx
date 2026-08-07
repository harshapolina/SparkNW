"use client";

import { cn } from "@/lib/utils";

/** Build Amazon-style page list: 1 … 4 5 6 … 20 */
export function buildPageItems(current: number, totalPages: number): Array<number | "ellipsis"> {
  if (totalPages <= 1) return totalPages === 1 ? [1] : [];
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  const pages = new Set<number>();
  pages.add(1);
  pages.add(totalPages);
  for (let p = current - 1; p <= current + 1; p++) {
    if (p >= 1 && p <= totalPages) pages.add(p);
  }
  // Keep a bit more context near edges
  if (current <= 3) {
    pages.add(2);
    pages.add(3);
    pages.add(4);
  }
  if (current >= totalPages - 2) {
    pages.add(totalPages - 1);
    pages.add(totalPages - 2);
    pages.add(totalPages - 3);
  }

  const sorted = [...pages].sort((a, b) => a - b);
  const out: Array<number | "ellipsis"> = [];
  for (let i = 0; i < sorted.length; i++) {
    const n = sorted[i];
    if (i > 0 && n - sorted[i - 1] > 1) out.push("ellipsis");
    out.push(n);
  }
  return out;
}

type Props = {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  className?: string;
};

export function NumberedPagination({ page, pageSize, total, onPageChange, className }: Props) {
  const totalPages = Math.max(1, Math.ceil(Math.max(0, total) / Math.max(1, pageSize)));
  const items = buildPageItems(page, totalPages);
  if (total <= 0 || totalPages <= 1) {
    return totalPages === 1 ? (
      <div className={cn("flex items-center gap-1", className)}>
        <span className="rounded-lg border border-white/20 bg-white px-2.5 py-1.5 text-xs font-semibold text-black">
          1
        </span>
      </div>
    ) : null;
  }

  return (
    <nav className={cn("flex flex-wrap items-center gap-1", className)} aria-label="Pagination">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        className="rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-zinc-400 disabled:opacity-35 hover:border-white/25 hover:text-zinc-200"
        aria-label="Previous page"
      >
        ‹
      </button>
      {items.map((item, idx) =>
        item === "ellipsis" ? (
          <span key={`e-${idx}`} className="px-1.5 text-xs text-zinc-600">
            …
          </span>
        ) : (
          <button
            key={item}
            type="button"
            onClick={() => onPageChange(item)}
            aria-current={item === page ? "page" : undefined}
            className={cn(
              "min-w-[2rem] rounded-lg border px-2.5 py-1.5 text-xs font-medium tabular",
              item === page
                ? "border-white/20 bg-white text-black"
                : "border-white/10 text-zinc-300 hover:border-white/25 hover:text-white"
            )}
          >
            {item}
          </button>
        )
      )}
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        className="rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-zinc-400 disabled:opacity-35 hover:border-white/25 hover:text-zinc-200"
        aria-label="Next page"
      >
        ›
      </button>
    </nav>
  );
}
