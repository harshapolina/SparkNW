const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export type UserRole = "admin" | "student";

export type Tokens = { access_token: string; refresh_token: string; token_type: string };
export type User = {
  id: string;
  email: string;
  name: string;
  avatar_url?: string | null;
  role?: UserRole;
  org_id?: string;
  profile_id?: string | null;
  student_id?: string | null;
  created_at: string;
};

export type StudentInfo = {
  timestamp?: string;
  full_name?: string;
  student_id?: string;
  program?: string;
  year_of_study?: string;
  mobile?: string;
  email?: string;
  university?: string;
  instagram_handle?: string;
  instagram_url?: string;
  instagram_username?: string;
  youtube_link?: string;
  youtube_username?: string;
  youtube_status?: string;
  created_content_before?: string;
  current_follower_count_raw?: string;
  instagram_followers_declared?: string;
  youtube_subscribers_declared?: string;
  why_join_spark?: string;
  content_interest?: string;
  uid?: string;
  duplicate_flag?: string;
  missing_info?: string;
};

export type Profile = {
  id: string;
  username: string;
  full_name?: string | null;
  bio?: string | null;
  website?: string | null;
  avatar_url?: string | null;
  is_verified: boolean;
  profile_url: string;
  followers: number;
  following: number;
  posts_count: number;
  /** Posts inside SPARK programme window (15 Jul 2026 → today). */
  programme_posts?: number;
  avg_likes: number;
  avg_views: number;
  avg_comments: number;
  engagement_rate: number;
  growth_pct_today: number;
  /** First scrape follower count in the programme window. */
  followers_baseline?: number | null;
  followers_baseline_date?: string | null;
  /** current − baseline (from first scrape we have). */
  followers_gained?: number;
  followers_gained_pct?: number;
  is_private?: boolean;
  is_business?: boolean;
  category?: string | null;
  highlight_reel_count?: number;
  follower_following_ratio?: number;
  insights?: Record<string, unknown>;
  student?: StudentInfo;
  scrape_progress?: {
    active?: boolean;
    phase?: string;
    scraped_posts?: number;
    total_posts?: number;
    posts_left?: number;
    percent?: number;
    source?: string;
    updated_at?: string;
  } | null;
  youtube_channel_id?: string | null;
  youtube_connected?: boolean;
  youtube_last_synced_at?: string | null;
  status: string;
  last_scraped_at?: string | null;
  last_success_at?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
};

function getToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("is_access_token");
}

export function setTokens(tokens: Tokens) {
  localStorage.setItem("is_access_token", tokens.access_token);
  localStorage.setItem("is_refresh_token", tokens.refresh_token);
}

export function clearTokens() {
  localStorage.removeItem("is_access_token");
  localStorage.removeItem("is_refresh_token");
  localStorage.removeItem("is_user");
}

export function saveUser(user: User) {
  localStorage.setItem("is_user", JSON.stringify(user));
}

export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("is_user");
  return raw ? (JSON.parse(raw) as User) : null;
}

export function getUserRole(user?: User | null): UserRole | null {
  const u = user ?? getStoredUser();
  if (!u?.role) return u ? "admin" : null;
  return u.role;
}

async function parseError(res: Response): Promise<string> {
  let detail = "Request failed";
  try {
    const data = await res.json();
    detail = data.detail || JSON.stringify(data);
  } catch {
    /* ignore */
  }
  return typeof detail === "string" ? detail : "Request failed";
}

/** Public fetch — never redirects to login on 401. */
export async function publicApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...options, headers });
  } catch (err) {
    const cause = err instanceof Error ? err.message : String(err);
    throw new Error(
      `Cannot reach API at ${API_URL} (${cause}). Check NEXT_PUBLIC_API_URL / CORS and that the API is running.`
    );
  }
  if (!res.ok) throw new Error(await parseError(res));
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...options, headers });
  } catch (err) {
    const cause = err instanceof Error ? err.message : String(err);
    // Native fetch throws TypeError("Failed to fetch") on network/CORS/timeout aborts
    throw new Error(
      `Cannot reach API at ${API_URL} (${cause}). Check NEXT_PUBLIC_API_URL / CORS, that the API is running, and that long scrapes are not blocking the request.`
    );
  }
  if (res.status === 401) {
    const detail = await parseError(res.clone());
    const isAuthAttempt =
      path.startsWith("/auth/login") ||
      path.startsWith("/auth/student-login") ||
      path.startsWith("/auth/signup");
    if (!isAuthAttempt) {
      clearTokens();
      if (typeof window !== "undefined") {
        const pathName = window.location.pathname;
        if (
          !pathName.startsWith("/login") &&
          !pathName.startsWith("/admin-login") &&
          !pathName.startsWith("/student-login") &&
          !pathName.startsWith("/top-10")
        ) {
          window.location.href = "/admin-login";
        }
      }
    }
    throw new Error(detail || "Unauthorized");
  }
  if (!res.ok) throw new Error(await parseError(res));
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}
