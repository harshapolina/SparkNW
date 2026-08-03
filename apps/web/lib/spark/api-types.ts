import type { LeaderboardSort } from "./types";

export type SparkCreatorRow = {
  id: string;
  profile_id: string;
  name: string;
  handle: string;
  username: string;
  initials: string;
  campus: string;
  team?: string | null;
  tier: "BRONZE" | "SILVER" | "GOLD";
  points: number;
  points_breakdown?: { consistency: number; performance: number; growth: number };
  followers: number;
  views: number;
  likes: number;
  comments: number;
  engagement: number;
  avg_likes: number;
  avg_views: number;
  avg_comments: number;
  posts_count: number;
  posts_7d: number;
  growth_pct_today: number;
  consistency_score: number;
  streak_weeks: string;
  grit_status: string;
  weeks_inactive: number;
  status: string;
  rank: number;
  prev_rank: number;
  rank_delta: number;
  next_tier?: string | null;
  points_to_next_tier?: number;
  task_history?: Array<{
    id: string;
    week: number;
    title: string;
    category: string;
    points: number;
    status: string;
    date: string;
    shortcode?: string | null;
  }>;
  is_you?: boolean;
  avatar_url?: string | null;
};

export type StudentDashboardResponse = {
  empty: boolean;
  week_label?: string;
  refresh_note?: string;
  creator?: SparkCreatorRow;
  top_creators?: SparkCreatorRow[];
  leaderboard?: SparkCreatorRow[];
  performance?: { date: string; views: number; points: number; followers: number }[];
  followers_delta?: number;
  task_history?: SparkCreatorRow["task_history"];
  total_participants?: number;
};

export type LeaderboardResponse = {
  items: SparkCreatorRow[];
  total: number;
  campuses: string[];
  sort: LeaderboardSort;
};

export type AdminOverviewResponse = {
  week_label: string;
  date_range: string;
  total_participants: number;
  ig_connected_pct: number;
  total_followers: number;
  total_views: number;
  total_likes: number;
  total_comments: number;
  total_points_distributed: number;
  /** Week-over-week % change in total SPARK points distributed */
  points_wow_pct: number;
  total_engagement: number;
  average_engagement: number;
  reels_posted: number;
  new_followers: number;
  growth_series: { date: string; followers: number; views: number; likes: number }[];
  insights: { label: string; name: string; value: string }[];
  needing_attention: { label: string; count: number }[];
  scrape: {
    tracked: number;
    updated_today: number;
    failed: number;
    last_sync: string | null;
    next_sync: string;
  };
  grit: { qualified: number; striking: number; at_risk: number };
  submissions: { pending: number; approved: number; rejected: number };
  at_risk_count: number;
  leaderboard_preview: SparkCreatorRow[];
};
