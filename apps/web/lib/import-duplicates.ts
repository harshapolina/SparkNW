export type ImportDuplicateItem = {
  url: string;
  username?: string;
  profile_id?: string;
  message?: string;
  imported_at: string;
};

const STORAGE_KEY = "instascope_import_duplicates";

export function loadImportDuplicates(): ImportDuplicateItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ImportDuplicateItem[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function appendImportDuplicates(items: ImportDuplicateItem[]): void {
  if (!items.length || typeof window === "undefined") return;
  const existing = loadImportDuplicates();
  const seen = new Set(existing.map((d) => d.profile_id || d.url));
  const merged = [...existing];
  for (const item of items) {
    const key = item.profile_id || item.url;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.unshift(item);
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(merged.slice(0, 5000)));
}

export function clearImportDuplicates(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(STORAGE_KEY);
}

export function saveDuplicatesFromImport(
  importItems: { url: string; username?: string; status: string; message?: string; profile_id?: string }[]
) {
  const dupes: ImportDuplicateItem[] = importItems
    .filter((i) => i.status === "duplicate")
    .map((i) => ({
      url: i.url,
      username: i.username,
      profile_id: i.profile_id,
      message: i.message,
      imported_at: new Date().toISOString(),
    }));
  appendImportDuplicates(dupes);
}
