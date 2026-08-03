/** SPARK Creator Accelerator — domain types */

export type Tier = "BRONZE" | "SILVER" | "GOLD";

export type Campus =
  | "NIAT"
  | "CDU"
  | "NIAT Hyderabad"
  | "NIAT Bengaluru"
  | "NIAT Chennai"
  | "CDU Vizag"
  | "Hyderabad"
  | "Bengaluru"
  | "Chennai"
  | "Pune"
  | "Delhi";

export type LeaderboardSort =
  | "overall"
  | "points"
  | "followers"
  | "views"
  | "engagement";

export type TaskStatus = "submitted" | "pending" | "approved" | "rejected" | "missed";

export type GritStatus = "qualified" | "striking" | "at_risk" | "not_eligible";

export interface SparkCreator {
  id: string;
  name: string;
  handle: string;
  initials: string;
  campus: Campus;
  team?: string;
  tier: Tier;
  points: number;
  followers: number;
  views: number;
  likes: number;
  comments: number;
  engagement: number; // %
  rank: number;
  prevRank: number;
  streakWeeks: string;
  isYou?: boolean;
  tags?: string[];
  gritStatus: GritStatus;
  weeksInactive: number;
  consistencyScore: number; // 0-100
}

export interface TaskHistoryItem {
  id: string;
  week: number;
  title: string;
  category: string;
  points: number;
  status: TaskStatus;
  date: string;
}

export interface WeeklyPoint {
  date: string;
  views: number;
  points: number;
  followers: number;
}

export interface StudentSnapshot {
  creator: SparkCreator;
  weekLabel: string;
  cohort: string;
  refreshNote: string;
  rankDelta: number;
  pointsToNextTier: number;
  nextTier: Tier | null;
  goldTarget: number;
  followersDelta: number;
  followersDeltaPct: number;
  viewsDeltaPct: number;
  engagementDeltaPct: number;
  postsThisWeek: number;
  postsDelta: number;
  avgViews: number;
  avgViewsDeltaPct: number;
  avgLikes: number;
  avgLikesDeltaPct: number;
  avgComments: number;
  avgCommentsDeltaPct: number;
  performance: WeeklyPoint[];
  taskHistory: TaskHistoryItem[];
  journalSubmitted: number;
  journalTotal: number;
  programmeStart: string;
  programmeEnd: string;
  youAreHere: string;
  totalParticipants: number;
}

export interface AdminOverview {
  weekLabel: string;
  dateRange: string;
  totalParticipants: number;
  participantsDelta: number;
  igConnectedPct: number;
  totalFollowers: number;
  followersDeltaPct: number;
  totalViews: number;
  viewsDeltaPct: number;
  totalLikes: number;
  likesDeltaPct: number;
  totalComments: number;
  reelsPosted: number;
  newFollowers: number;
  totalPointsDistributed: number;
  pointsDeltaPct: number;
  totalEngagement: number;
  engagementDeltaPct: number;
  growthSeries: { date: string; followers: number; views: number; likes: number }[];
  insights: { label: string; name: string; value: string }[];
  needingAttention: { label: string; count: number }[];
  scrape: {
    tracked: number;
    updatedToday: number;
    failed: number;
    lastSync: string;
    nextSync: string;
  };
  grit: { qualified: number; striking: number; atRisk: number };
  submissions: { pending: number; approved: number; rejected: number };
  atRiskCount: number;
}
