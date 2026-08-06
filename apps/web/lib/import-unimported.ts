/** Persist sheet rows that did not become new imports (missing IG, sheet dupes, API fail). */

import type { RejectedSheetRow } from "@/lib/student-sheet";

export type UnimportedItem = {
  id: string;
  row_number?: number;
  reason: string;
  reason_code: string;
  full_name?: string;
  student_id?: string;
  university?: string;
  email?: string;
  username?: string;
  raw_instagram?: string;
  url?: string;
  source: "parse" | "import";
  recorded_at: string;
};

const STORAGE_KEY = "instascope_import_unimported";

export function loadUnimported(): UnimportedItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as UnimportedItem[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function persist(items: UnimportedItem[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, 8000)));
}

export function appendUnimported(items: UnimportedItem[]): void {
  if (!items.length || typeof window === "undefined") return;
  const existing = loadUnimported();
  const seen = new Set(
    existing.map(
      (d) =>
        `${d.reason_code}|${d.student_id || ""}|${d.username || ""}|${d.raw_instagram || ""}|${d.row_number || ""}`
    )
  );
  const merged = [...existing];
  for (const item of items) {
    const key = `${item.reason_code}|${item.student_id || ""}|${item.username || ""}|${item.raw_instagram || ""}|${item.row_number || ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.unshift(item);
  }
  persist(merged);
}

export function clearUnimported(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(STORAGE_KEY);
}

export function saveUnimportedFromParse(rejected: RejectedSheetRow[], sheetLabel?: string): void {
  const now = new Date().toISOString();
  const items: UnimportedItem[] = rejected.map((r) => ({
    id: `parse-${r.row_number}-${r.reason_code}-${r.username || r.student.student_id || Math.random()}`,
    row_number: r.row_number,
    reason: sheetLabel ? `${r.reason} (${sheetLabel})` : r.reason,
    reason_code: r.reason_code,
    full_name: r.student.full_name,
    student_id: r.student.student_id,
    university: r.student.university,
    email: r.student.email,
    username: r.username,
    raw_instagram: r.raw_instagram,
    source: "parse",
    recorded_at: now,
  }));
  appendUnimported(items);
}

export function saveUnimportedFromImport(
  importItems: {
    url: string;
    username?: string;
    status: string;
    message?: string;
    profile_id?: string;
  }[]
): void {
  const now = new Date().toISOString();
  const items: UnimportedItem[] = importItems
    .filter((i) => i.status === "failed" || i.status === "skipped")
    .map((i) => ({
      id: `import-${i.status}-${i.username || i.url}-${now}`,
      reason: i.message || (i.status === "skipped" ? "Skipped" : "Import failed"),
      reason_code: i.status === "skipped" ? "skipped" : "failed",
      username: i.username,
      url: i.url,
      raw_instagram: i.url,
      source: "import",
      recorded_at: now,
    }));
  appendUnimported(items);
}

/** Download current unimported list as CSV. */
export function downloadUnimportedCsv(items: UnimportedItem[]): void {
  const headers = [
    "row_number",
    "reason",
    "reason_code",
    "full_name",
    "student_id",
    "university",
    "email",
    "username",
    "raw_instagram",
    "url",
    "source",
    "recorded_at",
  ];
  const esc = (v: unknown) => {
    const s = String(v ?? "");
    if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
    return s;
  };
  const lines = [
    headers.join(","),
    ...items.map((i) =>
      [
        i.row_number ?? "",
        i.reason,
        i.reason_code,
        i.full_name ?? "",
        i.student_id ?? "",
        i.university ?? "",
        i.email ?? "",
        i.username ?? "",
        i.raw_instagram ?? "",
        i.url ?? "",
        i.source,
        i.recorded_at,
      ]
        .map(esc)
        .join(",")
    ),
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `spark-unimported-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}
