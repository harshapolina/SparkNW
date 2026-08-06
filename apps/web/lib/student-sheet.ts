/** Map SPARK registration sheet columns → student dict (mirrors backend student_roster). */

export type SheetStudent = Record<string, string>;

const HEADER_ALIASES: Record<string, string[]> = {
  timestamp: ["timestamp"],
  full_name: ["full name", "fullname", "student name"],
  student_id: ["student id", "studentid", "roll no", "roll"],
  program: ["program/course", "program", "course"],
  year_of_study: ["year of study", "year"],
  mobile: ["mobile number", "mobile", "phone", "contact"],
  email: ["email address", "email"],
  university: ["university", "campus", "college"],
  instagram_handle: ["instagram handle link", "instagram handle", "ig handle"],
  instagram_url: ["instagram_url_clean", "instagram url clean", "instagram url", "instagram_url"],
  instagram_username: ["instagram_username", "instagram username"],
  youtube_link: ["youtube link", "youtube url"],
  youtube_username: ["youtube_username", "youtube username"],
  created_content_before: [
    "have you created content before",
    "created content before",
    "have you created",
    "created content",
  ],
  current_follower_count_raw: [
    "current follower count (insta and youtube)",
    "current follower count",
  ],
  instagram_followers_declared: ["instagram_followers", "instagram followers"],
  youtube_subscribers_declared: ["youtube_subscribers", "youtube subscribers"],
  why_join_spark: [
    "why do you want to join spark",
    "why do you want to join",
    "why join spark",
    "why join",
  ],
  content_interest: [
    "what type of content are you are interested in",
    "what type of content are you interested in",
    "type of content",
    "content interest",
    "interested in",
  ],
  uid: ["uid"],
  duplicate_flag: ["duplicate_flag", "duplicate flag", "duplicate"],
  missing_info: ["missing_info", "missing info", "missing"],
};

const EMPTY_CELLS = new Set(["", "nan", "none", "null"]);

const HANDLE_INVALID = new Set([
  "",
  "nan",
  "none",
  "null",
  "-",
  ".",
  "./",
  "na",
  "n/a",
  "nil",
  "yes",
  "no",
  "invites",
  "youtube missing",
]);

function normHeader(h: string): string {
  return h
    .trim()
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/["'`]/g, "")
    .replace(/[^\w\s/()+.-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isEmptyCell(text: string): boolean {
  return EMPTY_CELLS.has(text.trim().toLowerCase());
}

function isInvalidHandle(text: string): boolean {
  const t = text.trim().toLowerCase();
  if (HANDLE_INVALID.has(t)) return true;
  if (t.includes("suspended") || t.includes("not have") || t.includes("don't have") || t.includes("dont have"))
    return true;
  if (t.includes("no youtube") || t.includes("no instagram") || t.includes("no insta")) return true;
  return false;
}

export function extractUsername(raw: string): string {
  const v = raw.trim();
  if (!v) return "";
  if (v.startsWith("@")) return v.slice(1).toLowerCase();
  try {
    const withProto = v.includes("://") ? v : `https://${v}`;
    const u = new URL(withProto);
    if (u.hostname.includes("instagram.com") || u.hostname.includes("instagr.am")) {
      const part = u.pathname.split("/").filter(Boolean)[0] || "";
      return part.replace("@", "").toLowerCase();
    }
  } catch {
    /* plain username */
  }
  return v.replace(/^@/, "").toLowerCase();
}

function firstInstagramCandidate(raw: string): string {
  const text = raw.trim();
  if (!text || isInvalidHandle(text)) return "";
  const parts = text.split(/\s+(?:AND|and|&)\s+|,\s*(?=https?:\/\/|@)|;\s*/);
  for (const part of parts) {
    const cand = part.trim();
    if (!cand || isInvalidHandle(cand)) continue;
    if (cand.toLowerCase().includes("instagram.com")) {
      const m = cand.match(/https?:\/\/(?:www\.)?instagram\.com\/[A-Za-z0-9._]+\/?/i);
      if (m) return m[0].replace(/\/$/, "");
      return cand.split(/\s+/)[0];
    }
    if (cand.startsWith("@")) return cand;
    if (/^[A-Za-z0-9._]{1,30}$/.test(cand)) return cand;
  }
  return "";
}

export function resolveInstagramUrl(student: SheetStudent): string | null {
  const ordered = [student.instagram_username, student.instagram_url, student.instagram_handle];
  for (const raw of ordered) {
    const cand = firstInstagramCandidate(String(raw || ""));
    if (!cand) continue;
    const username = extractUsername(cand);
    if (!username) continue;
    if (["invites", "reel", "reels", "p", "explore", "stories"].includes(username)) continue;
    return `https://www.instagram.com/${username}`;
  }
  return null;
}

export function mapSheetRow(headers: string[], values: unknown[]): { student: SheetStudent; url: string } {
  const headerMap = new Map<string, number>();
  headers.forEach((h, i) => headerMap.set(normHeader(h), i));

  const student: SheetStudent = { youtube_status: "Coming soon" };

  for (const [field, aliases] of Object.entries(HEADER_ALIASES)) {
    for (const alias of aliases) {
      let idx = headerMap.get(normHeader(alias));
      if (idx === undefined) {
        for (const [hk, hi] of headerMap) {
          if (hk.includes(alias) || (alias.length >= 4 && alias.includes(hk))) {
            idx = hi;
            break;
          }
        }
      }
      if (idx === undefined || idx >= values.length) continue;
      const text = String(values[idx] ?? "").trim();
      if (text && !isEmptyCell(text)) {
        student[field] = text;
        break;
      }
    }
  }

  const url = resolveInstagramUrl(student) || "";
  if (url) {
    const username = extractUsername(url);
    if (username) {
      if (!student.instagram_username) student.instagram_username = username;
      if (!student.instagram_url) student.instagram_url = url;
    }
  }

  return { student, url };
}

export function parseSheetMatrix(matrix: string[][]): { url: string; username: string; student: SheetStudent }[] {
  if (!matrix.length) return [];
  const headers = matrix[0].map((c) => String(c ?? "").trim());
  const looksLikeHeader = headers.some((h) => {
    const n = normHeader(h);
    return (
      n.includes("instagram") ||
      n.includes("username") ||
      n.includes("full name") ||
      n.includes("timestamp") ||
      n.includes("student")
    );
  });

  const dataRows = looksLikeHeader ? matrix.slice(1) : matrix;
  const hdrs = looksLikeHeader ? headers : ["instagram_username"];
  const seen = new Set<string>();
  const out: { url: string; username: string; student: SheetStudent }[] = [];

  for (const row of dataRows) {
    const values = looksLikeHeader ? row : [row.find((c) => String(c || "").trim()) || ""];
    const mapped = mapSheetRow(hdrs, values);
    if (!mapped.url) continue;
    const username = extractUsername(mapped.url);
    if (!username || seen.has(username)) continue;
    seen.add(username);
    out.push({ url: mapped.url, username, student: mapped.student });
  }
  return out;
}
