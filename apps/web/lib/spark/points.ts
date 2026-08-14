/**
 * SPARK Point System — ranking & tier helpers.
 * Overall leaderboard rank = total SPARK points (desc).
 * Formula mirrors backend `spark_points.py` (source of truth).
 */

import type { LeaderboardSort, SparkCreator, Tier } from "./types";

export const TIER_THRESHOLDS: { tier: Tier; min: number }[] = [
  { tier: "BRONZE", min: 500 },
  { tier: "SILVER", min: 1500 },
  { tier: "GOLD", min: 2500 },
];

/** Short-form performance bands (views → pts) — Reels / YT Shorts */
export const SHORT_FORM_BANDS = [
  { min: 1_000, max: 10_000, pts: 5 },
  { min: 10_000, max: 50_000, pts: 15 },
  { min: 50_000, max: 100_000, pts: 30 },
  { min: 100_000, max: 500_000, pts: 60 },
] as const;

/** Long-form performance bands — ≥3 min YT or IG carousel */
export const LONG_FORM_BANDS = [
  { min: 500, max: 2_000, pts: 10 },
  { min: 2_000, max: 10_000, pts: 25 },
  { min: 10_000, max: 50_000, pts: 50 },
] as const;

/** Audience growth milestones (combined IG+YT for 1k–30k; 50k = single platform) */
export const GROWTH_MILESTONES = [
  { followers: 1_000, pts: 25 },
  { followers: 5_000, pts: 75 },
  { followers: 10_000, pts: 150 },
  { followers: 20_000, pts: 300 },
  { followers: 30_000, pts: 500 },
  { followers: 50_000, pts: 1000 }, // single platform + GRIT
] as const;

export const WEEKLY_CONSISTENCY_PTS = 10; // 2 shorts + 1 long-form per week
export const CONSISTENCY_CAP = 660;
export const PERFORMANCE_CAP = 3000;

export const CATEGORY_CAPS = {
  collaborations: 850,
  revenue: 3000,
  recognition: 500,
  participation: 470,
  monthly_bonuses: 1350,
} as const;

export function tierFromPoints(points: number): Tier {
  if (points >= 2500) return "GOLD";
  if (points >= 1500) return "SILVER";
  return "BRONZE";
}

export function pointsToNextTier(points: number): { next: Tier | null; remaining: number } {
  if (points < 500) return { next: "BRONZE", remaining: 500 - points };
  if (points < 1500) return { next: "SILVER", remaining: 1500 - points };
  if (points < 2500) return { next: "GOLD", remaining: 2500 - points };
  return { next: null, remaining: 0 };
}

export function shortFormPoints(views: number): number {
  for (let i = SHORT_FORM_BANDS.length - 1; i >= 0; i--) {
    const b = SHORT_FORM_BANDS[i];
    if (views >= b.min) return b.pts;
  }
  return 0;
}

export function longFormPoints(views: number): number {
  for (let i = LONG_FORM_BANDS.length - 1; i >= 0; i--) {
    const b = LONG_FORM_BANDS[i];
    if (views >= b.min) return b.pts;
  }
  return 0;
}

export function growthMilestonePoints(followers: number, alreadyAwarded: number[] = []): number {
  let total = 0;
  for (const m of GROWTH_MILESTONES) {
    if (followers >= m.followers && !alreadyAwarded.includes(m.followers)) {
      total += m.pts;
    }
  }
  return total;
}

export function movement(prevRank: number, rank: number): number {
  return prevRank - rank; // positive = moved up
}

export function sortCreators(list: SparkCreator[], sort: LeaderboardSort): SparkCreator[] {
  const copy = [...list];
  copy.sort((a, b) => {
    switch (sort) {
      case "followers":
        return b.followers - a.followers || b.points - a.points;
      case "views":
        return b.views - a.views || b.points - a.points;
      case "engagement":
        return b.engagement - a.engagement || b.points - a.points;
      case "points":
      case "overall":
      default:
        return b.points - a.points || b.followers - a.followers;
    }
  });
  return copy.map((c, i) => ({ ...c, rank: i + 1 }));
}

export function gritBucket(c: SparkCreator): "qualified" | "striking" | "at_risk" {
  if (c.gritStatus === "qualified") return "qualified";
  if (c.gritStatus === "striking") return "striking";
  return "at_risk";
}
