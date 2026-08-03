import type { QueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  AdminOverviewResponse,
  LeaderboardResponse,
  StudentDashboardResponse,
} from "@/lib/spark/api-types";

/** Prefetch SPARK APIs with the same query keys the pages use. */
export function prefetchSparkData(qc: QueryClient) {
  void qc.prefetchQuery({
    queryKey: ["spark", "student"],
    queryFn: () => api<StudentDashboardResponse>("/spark/student"),
  });
  void qc.prefetchQuery({
    queryKey: ["spark", "leaderboard", "overall"],
    queryFn: () => api<LeaderboardResponse>("/spark/leaderboard?sort=overall"),
  });
  void qc.prefetchQuery({
    queryKey: ["spark", "admin"],
    queryFn: () => api<AdminOverviewResponse>("/spark/admin"),
  });
}

export function sparkQueryKeyForApi(path: string): unknown[] | null {
  if (path.startsWith("/spark/student")) return ["spark", "student"];
  if (path.startsWith("/spark/admin") && !path.includes("leaderboard")) return ["spark", "admin"];
  if (path.startsWith("/spark/leaderboard")) {
    const sort = new URLSearchParams(path.split("?")[1] || "").get("sort") || "overall";
    return ["spark", "leaderboard", sort];
  }
  return null;
}
