import { dehydrate, hydrate, type Query, type QueryClient } from "@tanstack/react-query";

const STORAGE_KEY = "spark-query-cache-v2";
const MAX_AGE_MS = 30 * 60 * 1000;

function persistable(query: Query) {
  if (query.state.status !== "success") return false;
  const key = query.queryKey.map(String).join("|").toLowerCase();
  if (
    key.includes("sync-status") ||
    key.includes("scrape_progress") ||
    key.includes("scrape-progress") ||
    key.includes("|jobs|") ||
    key.endsWith("|jobs")
  ) {
    return false;
  }
  const head = String(query.queryKey[0] || "");
  return head === "spark" || head === "settings" || head === "notifications";
}

export function restoreQueryCache(client: QueryClient) {
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as { savedAt?: number; state?: unknown };
    if (!parsed?.savedAt || Date.now() - parsed.savedAt > MAX_AGE_MS || !parsed.state) return;
    hydrate(client, parsed.state);
  } catch {
    window.localStorage.removeItem(STORAGE_KEY);
  }
}

export function persistQueryCache(client: QueryClient) {
  if (typeof window === "undefined") return;
  try {
    const state = dehydrate(client, {
      shouldDehydrateQuery: persistable,
    });
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ savedAt: Date.now(), state }));
  } catch {
    // quota or private mode — ignore
  }
}

export function subscribeQueryCachePersist(client: QueryClient) {
  let timer: number | undefined;
  const flush = () => persistQueryCache(client);
  const unsub = client.getQueryCache().subscribe(() => {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(flush, 400);
  });
  return () => {
    if (timer) window.clearTimeout(timer);
    unsub();
  };
}
