"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  BookOpen,
  Calculator,
  Database,
  Layers,
  Medal,
  RefreshCw,
  Trophy,
  Workflow,
} from "lucide-react";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "scraping", label: "How scraping works" },
  { id: "averages", label: "Avg likes, views & more" },
  { id: "engagement", label: "Engagement & growth" },
  { id: "points", label: "SPARK points" },
  { id: "ranking", label: "How ranking works" },
  { id: "features", label: "Features map" },
  { id: "edge", label: "Edge cases" },
] as const;

function Formula({ children }: { children: React.ReactNode }) {
  return (
    <div className="my-3 overflow-x-auto rounded-xl border border-white/[0.08] bg-[#0c0c0c] px-4 py-3 font-mono text-[13px] text-lime-300/90">
      {children}
    </div>
  );
}

function Example({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-3 rounded-xl border border-sky-500/20 bg-sky-500/[0.06] px-4 py-3 text-sm text-sky-100/90">
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-sky-300/80">{title}</div>
      {children}
    </div>
  );
}

function DataTable({
  headers,
  rows,
}: {
  headers: string[];
  rows: (string | number)[][];
}) {
  return (
    <div className="mt-3 overflow-x-auto rounded-xl border border-white/[0.06]">
      <table className="w-full min-w-[320px] text-left text-sm">
        <thead className="bg-white/[0.03] text-[11px] uppercase tracking-wide text-zinc-500">
          <tr>
            {headers.map((h) => (
              <th key={h} className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-white/[0.04]">
              {row.map((cell, j) => (
                <td key={j} className="px-3 py-2 text-zinc-300 tabular-nums">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminHowItWorksPage() {
  const [active, setActive] = useState<string>("overview");

  useEffect(() => {
    const nodes = SECTIONS.map((s) => document.getElementById(s.id)).filter(Boolean) as HTMLElement[];
    if (!nodes.length) return;
    const obs = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible?.target?.id) setActive(visible.target.id);
      },
      { rootMargin: "-20% 0px -60% 0px", threshold: [0, 0.25, 0.5, 1] }
    );
    nodes.forEach((n) => obs.observe(n));
    return () => obs.disconnect();
  }, []);

  return (
    <div className="mx-auto flex max-w-6xl gap-8 lg:gap-10">
      <aside className="sticky top-6 hidden h-fit w-52 shrink-0 lg:block">
        <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
          <BookOpen size={12} /> Guide
        </div>
        <nav className="space-y-0.5">
          {SECTIONS.map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className={cn(
                "block rounded-lg px-3 py-2 text-[13px] transition",
                active === s.id
                  ? "bg-white/[0.06] text-white"
                  : "text-zinc-500 hover:bg-white/[0.03] hover:text-zinc-300"
              )}
            >
              {s.label}
            </a>
          ))}
        </nav>
      </aside>

      <div className="min-w-0 flex-1 space-y-12 pb-16">
        <header className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#ff3b30]">
            SPARK methodology
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">How SPARK works</h1>
          <p className="max-w-2xl text-sm leading-relaxed text-zinc-400">
            Everything on this site comes from live Instagram scrapes stored in MongoDB. This page
            explains scraping, how averages are calculated, how SPARK points and ranks are decided,
            and what each admin feature does.
          </p>
          <div className="flex flex-wrap gap-2 pt-1 text-xs">
            <Link href="/admin-scraping" className="rounded-full bg-white/[0.06] px-3 py-1.5 text-zinc-300 hover:bg-white/[0.1]">
              Scraping
            </Link>
            <Link href="/admin-leaderboard" className="rounded-full bg-white/[0.06] px-3 py-1.5 text-zinc-300 hover:bg-white/[0.1]">
              Leaderboard
            </Link>
            <Link href="/top-10" className="rounded-full bg-white/[0.06] px-3 py-1.5 text-zinc-300 hover:bg-white/[0.1]">
              Public Top 10
            </Link>
          </div>
        </header>

        {/* Overview */}
        <section id="overview" className="scroll-mt-8 space-y-4">
          <div className="flex items-center gap-2 text-[#ff3b30]">
            <Layers size={18} />
            <h2 className="text-xl font-semibold text-white">Overview</h2>
          </div>
          <p className="text-sm leading-relaxed text-zinc-400">
            SPARK is a cohort Instagram tracker for student creators. Admins import a roster, the
            system scrapes each Instagram profile, computes metrics from the scraped posts, then
            ranks creators with SPARK points.
          </p>
          <ol className="space-y-2 text-sm text-zinc-300">
            <li className="flex gap-3">
              <span className="font-mono text-[#ff3b30]">1</span>
              Import sheet → create profile rows (student + IG handle)
            </li>
            <li className="flex gap-3">
              <span className="font-mono text-[#ff3b30]">2</span>
              Bulk scrape queue runs one account at a time (sample, then deep)
            </li>
            <li className="flex gap-3">
              <span className="font-mono text-[#ff3b30]">3</span>
              Save card + posts → compute averages, engagement, growth
            </li>
            <li className="flex gap-3">
              <span className="font-mono text-[#ff3b30]">4</span>
              Leaderboard / Public Top 10 rank by SPARK points (or other sorts)
            </li>
          </ol>
          <div className="rounded-2xl border border-white/[0.06] bg-[#121212] p-4 text-sm text-zinc-400">
            <div className="mb-2 flex items-center gap-2 text-zinc-200">
              <Database size={14} /> Where data lives
            </div>
            <ul className="space-y-1.5 text-[13px]">
              <li>
                <span className="text-zinc-200">profiles</span> — followers, following, posts_count, averages, status
              </li>
              <li>
                <span className="text-zinc-200">posts</span> — each post/reel (likes, comments, views, type, caption)
              </li>
              <li>
                <span className="text-zinc-200">profile_snapshots</span> — daily history for growth charts & rank delta
              </li>
              <li>
                <span className="text-zinc-200">jobs / scrape_logs</span> — scrape run records
              </li>
            </ul>
          </div>
        </section>

        {/* Scraping */}
        <section id="scraping" className="scroll-mt-8 space-y-4">
          <div className="flex items-center gap-2 text-[#ff3b30]">
            <RefreshCw size={18} />
            <h2 className="text-xl font-semibold text-white">How scraping works</h2>
          </div>
          <p className="text-sm leading-relaxed text-zinc-400">
            Bulk scrapes are <strong className="font-medium text-zinc-200">sequential</strong> (one
            profile at a time) with a delay between jobs so Instagram rate-limits less often.
          </p>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">Two-phase bulk flow</h3>
          <DataTable
            headers={["Phase", "What it does", "Post cap"]}
            rows={[
              ["1 · Sample", "Fast pass for every queued account — card + recent posts", "~48 (SCRAPE_BULK_MAX_POSTS)"],
              ["2 · Deep", "Auto full timeline for accounts that still have more posts", "Uncapped (all public posts)"],
            ]}
          />
          <p className="text-sm text-zinc-400">
            Sample jobs always finish before deep jobs, so the roster fills quickly first.
          </p>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">Per-account path</h3>
          <ol className="list-decimal space-y-2 pl-5 text-sm text-zinc-300">
            <li>HTTP profile card (followers / following / posts_count)</li>
            <li>Paginate timeline (username feed / web profile) up to the active cap</li>
            <li>Optional browser only if HTTP is incomplete and browser is enabled</li>
            <li>Save result → recompute averages → clear progress → next account</li>
          </ol>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">Single Refresh / Add</h3>
          <p className="text-sm text-zinc-400">
            Admin <strong className="font-medium text-zinc-200">Refresh</strong> on one profile uses
            the single-scrape path (can run alongside bulk with a lease). It is not the same queue as
            bulk import.
          </p>

          <div className="rounded-2xl border border-dashed border-white/[0.1] bg-[#121212] p-4 font-mono text-[12px] leading-relaxed text-zinc-400">
            Import 505 IDs
            <br />
            → sample queue (1…505)
            <br />
            → for each: scrape ≤48 posts → if more posts left → deep queue
            <br />
            → after samples: deep full timelines
            <br />
            → delay ~20s between jobs (SCRAPE_BULK_DELAY_SECONDS)
          </div>
        </section>

        {/* Averages */}
        <section id="averages" className="scroll-mt-8 space-y-4">
          <div className="flex items-center gap-2 text-[#ff3b30]">
            <Calculator size={18} />
            <h2 className="text-xl font-semibold text-white">How averages are calculated</h2>
          </div>
          <p className="text-sm leading-relaxed text-zinc-400">
            After a scrape saves posts, SPARK computes portfolio metrics from{" "}
            <strong className="font-medium text-zinc-200">only the posts we scraped</strong> (the
            sample set). We do not invent numbers — every average is a mean over that set.
          </p>

          <h3 className="pt-1 text-sm font-semibold text-zinc-200">Mean (simple average)</h3>
          <Formula>mean(values) = sum(values) ÷ count(values)</Formula>
          <p className="text-sm text-zinc-400">If there are no posts, all averages are 0.</p>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">Avg likes</h3>
          <Formula>avg_likes = mean(likes of every scraped post)</Formula>
          <Example title="Example">
            Posts scraped: 100, 200, 50 likes → avg likes = (100 + 200 + 50) ÷ 3 = <strong>116.67</strong>
          </Example>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">Avg comments</h3>
          <Formula>avg_comments = mean(comments of every scraped post)</Formula>
          <Example title="Example">
            Comments: 10, 20, 0 → avg comments = 30 ÷ 3 = <strong>10</strong>
          </Example>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">Avg views (special rule)</h3>
          <p className="text-sm text-zinc-400">
            Views are often missing on photos. We only include posts whose{" "}
            <code className="rounded bg-white/[0.06] px-1 text-[12px] text-zinc-200">views ≥ 10</code>
            {" "}so zeros / missing view fields do not crush the average.
          </p>
          <Formula>avg_views = mean(views where views ≥ 10)</Formula>
          <p className="text-sm text-zinc-400">
            If no post has views ≥ 10, avg views = 0.
          </p>
          <Example title="Example">
            Views: 0 (photo), 5 (ignored), 12_000, 8_000 → avg views = (12000 + 8000) ÷ 2 ={" "}
            <strong>10_000</strong>
          </Example>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">Avg reel views</h3>
          <p className="text-sm text-zinc-400">
            Same ≥10 rule, but only on reel / video posts.
          </p>
          <Formula>avg_reel_views = mean(views of reels/videos where views ≥ 10)</Formula>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">Other derived fields</h3>
          <DataTable
            headers={["Metric", "How it is calculated"]}
            rows={[
              ["sampled_posts", "Count of posts in this scrape set"],
              ["total_likes_sampled", "Sum of likes across scraped posts"],
              ["total_comments_sampled", "Sum of comments across scraped posts"],
              ["total_views_sampled", "Sum of views only where views ≥ 10"],
              ["median_likes", "Middle value when likes are sorted"],
              ["max_likes / min_likes", "Highest / lowest likes in the set"],
              ["best / worst post", "Post with highest / lowest likes"],
              ["posts_last_7d / 30d", "Scraped posts with posted_at in that window"],
              ["posting_frequency_per_week", "dated_posts ÷ (span_days ÷ 7)"],
              ["like_follower_ratio", "(avg_likes ÷ followers) × 100"],
              ["comment_follower_ratio", "(avg_comments ÷ followers) × 100"],
              ["comments_to_likes_ratio", "(total comments ÷ total likes) × 100"],
              ["video_share_pct", "% of scraped posts that are video/reel"],
              ["image / reel / carousel counts", "Count by media_type in the sample"],
            ]}
          />
          <p className="text-sm text-zinc-500">
            Important: if bulk only sampled 48 of 2000 posts, averages are over those 48 — not the
            full account — until the deep scrape finishes.
          </p>
        </section>

        {/* Engagement & growth */}
        <section id="engagement" className="scroll-mt-8 space-y-4">
          <div className="flex items-center gap-2 text-[#ff3b30]">
            <Workflow size={18} />
            <h2 className="text-xl font-semibold text-white">Engagement & growth</h2>
          </div>

          <h3 className="text-sm font-semibold text-zinc-200">Engagement rate (%)</h3>
          <Formula>engagement_rate = ((avg_likes + avg_comments) ÷ followers) × 100</Formula>
          <p className="text-sm text-zinc-400">If followers ≤ 0, engagement = 0.</p>
          <Example title="Example">
            avg likes 116.67, avg comments 10, followers 2_000 → ((116.67 + 10) ÷ 2000) × 100 ={" "}
            <strong>6.3335%</strong>
          </Example>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">Growth % today</h3>
          <p className="text-sm text-zinc-400">
            Compared to the previous follower count stored on the profile before this scrape:
          </p>
          <Formula>growth_pct = ((current_followers − previous_followers) ÷ previous_followers) × 100</Formula>
          <ul className="list-disc space-y-1 pl-5 text-sm text-zinc-400">
            <li>If previous was 0 and current is 0 → 0%</li>
            <li>If previous was 0 and current &gt; 0 → 100%</li>
          </ul>
          <Example title="Example">
            Was 1_000 followers, now 1_050 → ((1050 − 1000) ÷ 1000) × 100 = <strong>5%</strong>
          </Example>
          <p className="text-sm text-zinc-400">
            Daily snapshots also power charts and “rank vs last week” on the leaderboard.
          </p>
        </section>

        {/* SPARK points */}
        <section id="points" className="scroll-mt-8 space-y-4">
          <div className="flex items-center gap-2 text-[#ff3b30]">
            <Trophy size={18} />
            <h2 className="text-xl font-semibold text-white">SPARK points</h2>
          </div>
          <p className="text-sm leading-relaxed text-zinc-400">
            Leaderboard “overall” score is SPARK points from scraped posts + follower milestones:
          </p>
          <Formula>SPARK points = consistency + min(performance, 3000) + growth_milestones</Formula>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">1) Consistency (0 or +10)</h3>
          <p className="text-sm text-zinc-400">In the last 7 days (by post date):</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-zinc-300">
            <li>≥ 2 short posts and ≥ 1 long/carousel, <em>or</em></li>
            <li>≥ 3 posts total</li>
          </ul>
          <p className="text-sm text-zinc-400">→ award <strong className="text-zinc-200">+10</strong>, else 0.</p>
          <p className="text-sm text-zinc-500">
            Long-form = carousel, or video with caption longer than 280 characters. Everything else
            uses short-form view bands.
          </p>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">2) Performance (sum per post, capped at 3000)</h3>
          <p className="text-sm text-zinc-400">Each post scores from its view count:</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                Short / reel bands
              </div>
              <DataTable
                headers={["Views ≥", "Points"]}
                rows={[
                  ["100,000", "60"],
                  ["50,000", "30"],
                  ["10,000", "15"],
                  ["1,000", "5"],
                  ["below 1,000", "0"],
                ]}
              />
            </div>
            <div>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                Long / carousel bands
              </div>
              <DataTable
                headers={["Views ≥", "Points"]}
                rows={[
                  ["10,000", "50"],
                  ["2,000", "25"],
                  ["500", "10"],
                  ["below 500", "0"],
                ]}
              />
            </div>
          </div>
          <p className="text-sm text-zinc-400">
            Only the highest matching band applies per post (not stacked). All post points are
            summed, then capped at <strong className="text-zinc-200">3000</strong>.
          </p>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">3) Growth milestones (followers)</h3>
          <p className="text-sm text-zinc-400">
            Points are the <strong className="text-zinc-200">sum of all unlocked</strong> milestones
            (not only the highest):
          </p>
          <DataTable
            headers={["Followers ≥", "Points added"]}
            rows={[
              ["1,000", "25"],
              ["5,000", "75"],
              ["10,000", "150"],
              ["20,000", "300"],
              ["30,000", "500"],
              ["50,000", "1,000"],
            ]}
          />
          <Example title="Example">
            12_000 followers unlocks 1k + 5k + 10k → 25 + 75 + 150 = <strong>250</strong> growth
            points.
          </Example>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">Tiers</h3>
          <DataTable
            headers={["Tier", "Points"]}
            rows={[
              ["BRONZE", "below 1,500"],
              ["SILVER", "1,500 – 2,499"],
              ["GOLD", "2,500+"],
            ]}
          />
        </section>

        {/* Ranking */}
        <section id="ranking" className="scroll-mt-8 space-y-4">
          <div className="flex items-center gap-2 text-[#ff3b30]">
            <Medal size={18} />
            <h2 className="text-xl font-semibold text-white">How ranking is decided</h2>
          </div>
          <p className="text-sm leading-relaxed text-zinc-400">
            The leaderboard builds a row per creator (points + metrics), then sorts.
          </p>
          <DataTable
            headers={["Sort mode", "Order (highest first)"]}
            rows={[
              ["Overall / Points", "SPARK points → followers → views"],
              ["Followers", "Followers → points"],
              ["Views", "Total views (from scored posts) → points"],
              ["Engagement", "Engagement % → points"],
            ]}
          />
          <ul className="list-disc space-y-2 pl-5 text-sm text-zinc-300">
            <li>
              <strong className="text-zinc-200">Rank</strong> = position after sort (1 = best)
            </li>
            <li>
              <strong className="text-zinc-200">Prev rank</strong> ≈ rank from snapshots ~7 days ago
              (or at the start of a selected date range)
            </li>
            <li>
              <strong className="text-zinc-200">Rank delta</strong> = prev_rank − current_rank
              (positive = moved up)
            </li>
            <li>
              <strong className="text-zinc-200">Public Top 10</strong> = first 10 rows of overall
              sort
            </li>
            <li>
              <strong className="text-zinc-200">Date range</strong> on the leaderboard only scores
              posts inside that window (when both dates are set)
            </li>
          </ul>
        </section>

        {/* Features */}
        <section id="features" className="scroll-mt-8 space-y-4">
          <div className="flex items-center gap-2 text-[#ff3b30]">
            <Layers size={18} />
            <h2 className="text-xl font-semibold text-white">Features map</h2>
          </div>
          <DataTable
            headers={["Feature", "What it does"]}
            rows={[
              ["Dashboard", "Cohort overview — counts, recent activity, health"],
              ["Leaderboard", "Full SPARK ranks, campus filters, date range, sort modes"],
              ["Scraping", "Profile list, live scrape progress, Refresh / Pause / Delete"],
              ["Analytics", "Trends from snapshots (followers, engagement over time)"],
              ["Alerts", "Notifications for scrape fails, growth, engagement spikes"],
              ["Import roster", "Upload sheet → create student profiles + queue scrapes"],
              ["Unimported", "Sheet rows that did not import (missing/invalid IG, dupes)"],
              ["Settings", "Alert thresholds (growth %, engagement spike %), timezone"],
              ["Public Top 10", "Public live board of the top 10 overall"],
              ["How it works", "This methodology page"],
              ["Student portal", "Student sees own rank, dashboard, public board"],
            ]}
          />
          <p className="text-sm text-zinc-400">
            Shared rule: admin and student portals read the{" "}
            <strong className="text-zinc-200">same scraped MongoDB data</strong> — rankings are not
            separate demos.
          </p>
        </section>

        {/* Edge cases */}
        <section id="edge" className="scroll-mt-8 space-y-4">
          <div className="flex items-center gap-2 text-[#ff3b30]">
            <Workflow size={18} />
            <h2 className="text-xl font-semibold text-white">Edge cases</h2>
          </div>
          <DataTable
            headers={["Situation", "What SPARK does"]}
            rows={[
              ["Instagram handle missing / not found", "Mark unavailable — skip deep — next account"],
              ["Confirmed 0 posts", "Save card as success (active) with zeros — no deep needed"],
              ["Private account", "Save what IG allows (often card only, few/no posts)"],
              ["Rate limit / timeout", "Fail or interrupt; do not wipe good existing data"],
              ["Incomplete scrape vs existing data", "Refuse to overwrite a good profile with empty junk"],
              ["Sample then deep", "Averages update again when deep finishes with more posts"],
              ["API restart mid-bulk", "Worker can resume / re-queue unfinished zero-data rows"],
            ]}
          />
          <p className="text-sm text-zinc-500">
            If a profile shows Failed with 0 followers and 0 posts, use Refresh after the latest
            API build — empty confirmed accounts should save cleanly, and missing handles should
            show as unavailable instead of hanging.
          </p>
        </section>

        <footer className="border-t border-white/[0.06] pt-6 text-xs text-zinc-600">
          Formulas match the live backend in{" "}
          <code className="text-zinc-500">instascope_shared/analytics/metrics.py</code>,{" "}
          <code className="text-zinc-500">domain/instagram.py</code>, and{" "}
          <code className="text-zinc-500">services/spark.py</code>.
        </footer>
      </div>
    </div>
  );
}
