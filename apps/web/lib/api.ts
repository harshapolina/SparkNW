const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export type Tokens = { access_token: string; refresh_token: string; token_type: string };
export type User = { id: string; email: string; name: string; avatar_url?: string | null; created_at: string };

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
  avg_likes: number;
  avg_views: number;
  avg_comments: number;
  engagement_rate: number;
  growth_pct_today: number;
  is_private?: boolean;
  is_business?: boolean;
  category?: string | null;
  highlight_reel_count?: number;
  follower_following_ratio?: number;
  insights?: Record<string, unknown>;
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

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearTokens();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    let detail = "Request failed";
    try {
      const data = await res.json();
      detail = data.detail || JSON.stringify(data);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}
