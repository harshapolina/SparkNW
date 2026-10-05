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

const SELECTION_KEY = "admin-scraping-selection-v1";

export type AdminScrapingSelection = { q: string; status: string; ids: string[] };

export function readAdminScrapingSelectionRecord(): AdminScrapingSelection | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(SELECTION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { q?: unknown; status?: unknown; ids?: unknown };
    const ids = Array.isArray(parsed.ids)
      ? [...new Set(parsed.ids.filter((id): id is string => typeof id === "string" && id.length > 0))]
      : [];
    return {
      q: typeof parsed.q === "string" ? parsed.q : "",
      status: typeof parsed.status === "string" ? parsed.status : "",
      ids,
    };
  } catch {
    return null;
  }
}

/** Remember checked creator ids for the current search + status, across pages. */
export function readAdminScrapingSelection(q: string, status: string): string[] {
  const stored = readAdminScrapingSelectionRecord();
  if (!stored || stored.q !== q || stored.status !== status) return [];
  return stored.ids;
}

export function writeAdminScrapingSelection(state: { q: string; status: string; ids: string[] }) {
  try {
    sessionStorage.setItem(
      SELECTION_KEY,
      JSON.stringify({
        q: state.q,
        status: state.status,
        ids: [...new Set(state.ids.filter(Boolean))],
      })
    );
  } catch {
    /* ignore */
  }
}

/** Add or remove only this page's ids. Selections on other pages stay. */
export function togglePageSelection(selected: string[], pageIds: string[], checked: boolean): string[] {
  if (checked) {
    const have = new Set(selected);
    const next = [...selected];
    for (const id of pageIds) {
      if (!have.has(id)) {
        have.add(id);
        next.push(id);
      }
    }
    return next;
  }
  const drop = new Set(pageIds);
  return selected.filter((id) => !drop.has(id));
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
