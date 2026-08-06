import type { StudentInfo } from "@/lib/api";

/** All SPARK sheet columns for list/detail views (order matches registration sheet). */
export const STUDENT_SHEET_COLUMNS: { key: keyof StudentInfo; label: string }[] = [
  { key: "timestamp", label: "Timestamp" },
  { key: "full_name", label: "Full Name" },
  { key: "student_id", label: "Student ID" },
  { key: "program", label: "Program/Course" },
  { key: "year_of_study", label: "Year of Study" },
  { key: "mobile", label: "Mobile Number" },
  { key: "email", label: "Email Address" },
  { key: "university", label: "University" },
  { key: "instagram_handle", label: "Instagram Handle Link" },
  { key: "instagram_url", label: "Instagram URL" },
  { key: "instagram_username", label: "Instagram Username" },
  { key: "youtube_link", label: "YouTube Link" },
  { key: "youtube_username", label: "YouTube Username" },
  { key: "created_content_before", label: "Created Content Before?" },
  { key: "current_follower_count_raw", label: "Follower Count (Declared)" },
  { key: "instagram_followers_declared", label: "Instagram Followers" },
  { key: "youtube_subscribers_declared", label: "YouTube Subscribers" },
  { key: "why_join_spark", label: "Why join Spark?" },
  { key: "content_interest", label: "Content Interest" },
  { key: "uid", label: "UID" },
  { key: "duplicate_flag", label: "Duplicate Flag" },
  { key: "missing_info", label: "Missing Info" },
  { key: "youtube_status", label: "YouTube Status" },
];

/** Compact fields shown in the profile header (everything else → Student tab). */
export const STUDENT_HEADER_KEYS = new Set<keyof StudentInfo>([
  "full_name",
  "student_id",
  "university",
]);

export function studentFieldValue(s: StudentInfo | undefined, key: keyof StudentInfo): string {
  if (!s) return "";
  const v = s[key];
  return v != null && String(v).trim() ? String(v) : "";
}

/** Full sheet fields for the Student tab (aligned label → value rows). */
export function studentDetailFields(s: StudentInfo | undefined | null): [string, string][] {
  if (!s) return [];
  return STUDENT_SHEET_COLUMNS.map(({ key, label }) => [label, studentFieldValue(s, key)]);
}

/** Fields not already shown in the profile header summary. */
export function studentDetailFieldsExtra(s: StudentInfo | undefined | null): [string, string][] {
  if (!s) return [];
  return STUDENT_SHEET_COLUMNS.filter(({ key }) => !STUDENT_HEADER_KEYS.has(key)).map(({ key, label }) => [
    label,
    studentFieldValue(s, key),
  ]);
}
