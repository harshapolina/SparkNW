import type { StudentInfo } from "@/lib/api";

/** All SPARK sheet columns for list/detail views. */
export const STUDENT_SHEET_COLUMNS: { key: keyof StudentInfo | "instagram_display"; label: string }[] = [
  { key: "timestamp", label: "Timestamp" },
  { key: "full_name", label: "Full name" },
  { key: "student_id", label: "Student ID" },
  { key: "program", label: "Program/Course" },
  { key: "year_of_study", label: "Year of study" },
  { key: "mobile", label: "Mobile" },
  { key: "email", label: "Email" },
  { key: "university", label: "University" },
  { key: "instagram_handle", label: "Instagram handle" },
  { key: "instagram_url", label: "Instagram URL" },
  { key: "instagram_username", label: "Instagram username" },
  { key: "youtube_link", label: "YouTube link" },
  { key: "youtube_username", label: "YouTube username" },
  { key: "created_content_before", label: "Created content before?" },
  { key: "current_follower_count_raw", label: "Follower count (declared)" },
  { key: "instagram_followers_declared", label: "Instagram followers" },
  { key: "youtube_subscribers_declared", label: "YouTube subscribers" },
  { key: "content_interest", label: "Content interest" },
  { key: "uid", label: "UID" },
  { key: "duplicate_flag", label: "Duplicate flag" },
  { key: "missing_info", label: "Missing info" },
];

export function studentFieldValue(s: StudentInfo | undefined, key: (typeof STUDENT_SHEET_COLUMNS)[number]["key"]): string {
  if (!s) return "";
  if (key === "instagram_display") {
    return s.instagram_username || s.instagram_handle || s.instagram_url || "";
  }
  const v = s[key];
  return v != null && String(v).trim() ? String(v) : "";
}

export function studentDetailFields(s: StudentInfo): [string, string][] {
  const rows: [string, string][] = STUDENT_SHEET_COLUMNS.map(({ key, label }) => [
    label,
    studentFieldValue(s, key),
  ]);
  rows.push(["Why join Spark?", s.why_join_spark || ""]);
  rows.push(["YouTube status", s.youtube_status || "Coming soon"]);
  return rows;
}
