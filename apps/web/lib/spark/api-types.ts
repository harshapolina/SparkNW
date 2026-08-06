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
  points_breakdown?: { consistency: number; performance: number; growth: number; bonus?: number };
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

export type LeaderboardResponse = {
  items: SparkCreatorRow[];
  total: number;
  campuses: string[];
  sort: LeaderboardSort;
  you?: SparkCreatorRow | null;
  in_top_10?: boolean;
  /** Inclusive period start when date-range filter is applied */
  from_date?: string | null;
  /** Inclusive period end when date-range filter is applied */
  to_date?: string | null;
};

export type Top10Response = {
  items: SparkCreatorRow[];
  total_creators: number;
  week_label?: string;
};

export type AdminAlert = {
  id: string;
  type: string;
  severity: string;
  title: string;
  body: string;
  profile_id: string;
  username: string;
  created_at: string;
};

export type AdminRecentProfile = {
  id: string;
  username: string;
  full_name?: string | null;
  followers: number;
  following: number;
  posts_count: number;
  avg_likes: number;
  avg_views: number;
  avg_comments?: number;
  engagement_rate: number;
  growth_pct_today: number;
  status: string;
  is_verified: boolean;
  is_private: boolean;
  is_business?: boolean;
  category?: string | null;
  bio?: string | null;
  website?: string | null;
  follower_following_ratio?: number;
  highlight_reel_count?: number;
  last_scraped_at: string | null;
  last_error?: string | null;
  student_id?: string | null;
  campus?: string;
  full_name_student?: string | null;
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
  average_followers?: number;
  average_likes?: number;
  average_views?: number;
  follower_growth_today?: number;
  profiles_updated_today?: number;
  failed_updates?: number;
  reels_posted: number;
  new_followers: number;
  growth_series: { date: string; followers: number; views: number; likes: number }[];
  followers_over_time?: { date: string; value: number }[];
  content_types?: { name: string; value: number }[];
  posts_per_day?: { date: string; value: number }[];
  posting_heatmap?: { day: number; hour: number; count: number }[];
  recent_updates?: AdminRecentProfile[];
  portfolio?: AdminRecentProfile[];
  alerts?: AdminAlert[];
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

export type StudentDashboardResponse = {
  empty: boolean;
  week_label?: string;
  refresh_note?: string;
  creator?: SparkCreatorRow;
  top_creators?: SparkCreatorRow[];
  leaderboard?: SparkCreatorRow[];
  performance?: {
    date: string;
    views: number;
    points: number;
    followers: number;
    likes?: number;
    engagement?: number;
  }[];
  followers_delta?: number;
  task_history?: SparkCreatorRow["task_history"];
  total_participants?: number;
  in_top_10?: boolean;
  insights?: Record<string, unknown>;
  recent_posts?: Array<{
    id: string;
    shortcode: string;
    media_type: string;
    caption?: string;
    likes: number;
    comments: number;
    views: number;
    posted_at?: string | null;
    permalink?: string | null;
  }>;
  history?: Array<{
    id: string;
    snapshot_date: string;
    followers: number;
    following: number;
    posts_count: number;
    avg_likes: number;
    avg_views: number;
    engagement_rate: number;
    followers_growth: number;
    followers_growth_pct: number;
  }>;
  profile?: {
    bio?: string | null;
    website?: string | null;
    is_verified?: boolean;
    is_private?: boolean;
    is_business?: boolean;
    category?: string | null;
    following?: number;
    student?: Record<string, unknown>;
    last_scraped_at?: string | null;
  };
};
