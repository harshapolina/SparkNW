import type { QueryClient } from "@tanstack/react-query";
import { api, publicApi } from "@/lib/api";
import type {
  AdminOverviewResponse,
  LeaderboardResponse,
  StudentDashboardResponse,
  Top10Response,
} from "@/lib/spark/api-types";
import { defaultCohortRange, utcTodayYmd } from "@/lib/spark/cohort";

/** Prefetch only the student dashboard payload. Leaderboard/top-10 wait until those pages. */
export function prefetchStudentSpark(qc: QueryClient) {
  void qc.prefetchQuery({
    queryKey: ["spark", "student"],
    queryFn: () => api<StudentDashboardResponse>("/spark/student"),
  });
}

export function prefetchAdminSpark(qc: QueryClient) {
  const range = defaultCohortRange(utcTodayYmd());
  void qc.prefetchQuery({
    queryKey: ["spark", "admin"],
    queryFn: () => api<AdminOverviewResponse>("/spark/admin"),
  });
  void qc.prefetchQuery({
    queryKey: ["spark", "leaderboard", "overall", range.from, range.to],
    queryFn: () =>
      api<LeaderboardResponse>(
        `/spark/leaderboard?sort=overall&from_date=${range.from}&to_date=${range.to}`
      ),
  });
  void qc.prefetchQuery({
    queryKey: ["spark", "top-10", "public"],
    queryFn: () => publicApi<Top10Response>("/spark/top-10"),
  });
}

export function prefetchSparkData(qc: QueryClient) {
  prefetchStudentSpark(qc);
  prefetchAdminSpark(qc);
}

export function sparkQueryKeyForApi(path: string): unknown[] | null {
  const range = defaultCohortRange(utcTodayYmd());
  if (path.startsWith("/spark/student")) return ["spark", "student"];
  if (path.startsWith("/spark/admin") && !path.includes("leaderboard")) return ["spark", "admin"];
  if (path.startsWith("/spark/top-10")) return ["spark", "top-10", "public"];
  if (path.startsWith("/spark/leaderboard")) {
    const sort = new URLSearchParams(path.split("?")[1] || "").get("sort") || "overall";
    return ["spark", "leaderboard", sort, range.from, range.to];
  }
  return null;
}
