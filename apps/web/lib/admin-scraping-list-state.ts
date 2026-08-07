/** Persist scraping board page/filter so profile → back returns to the same page. */

const LIST_STATE_KEY = "admin-scraping-list-v1";

export type AdminScrapingListState = {
  page: number;
  q: string;
  status: string;
};

export function readAdminScrapingListState(): AdminScrapingListState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(LIST_STATE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { page?: unknown; q?: unknown; status?: unknown };
    return {
      page: Math.max(1, Number(parsed.page) || 1),
      q: typeof parsed.q === "string" ? parsed.q : "",
      status: typeof parsed.status === "string" ? parsed.status : "",
    };
  } catch {
    return null;
  }
}

export function writeAdminScrapingListState(state: AdminScrapingListState) {
  try {
    sessionStorage.setItem(LIST_STATE_KEY, JSON.stringify(state));
  } catch {
    /* ignore */
  }
}

export function adminScrapingListHref(): string {
  const stored = readAdminScrapingListState();
  if (!stored) return "/admin-scraping";
  const params = new URLSearchParams();
  if (stored.q.trim()) params.set("q", stored.q.trim());
  if (stored.status) params.set("status", stored.status);
  if (stored.page > 1) params.set("page", String(stored.page));
  const qs = params.toString();
  return qs ? `/admin-scraping?${qs}` : "/admin-scraping";
}
