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
import { ProgrammeWindowNote } from "@/components/programme-window-note";
import { PROGRAMME_STARTED_LABEL } from "@/lib/spark/cohort";

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
          <ProgrammeWindowNote />
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
            SPARK is a cohort creator tracker (Instagram + YouTube). Admins import a roster, the
            system scrapes / syncs public metrics, then ranks creators on the overall leaderboard
            with SPARK points.
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

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">Daily auto-scrape (08:00 IST)</h3>
          <p className="text-sm text-zinc-400">
            On production (Hetzner), Celery Beat runs on the server every day at{" "}
            <span className="text-zinc-200">08:00 Asia/Kolkata</span> and queues a programme-window
            scrape for every <span className="text-zinc-200">ACTIVE</span> account, including private
            ones. If a private account is public that morning, the scrape clears the private flag and
            it moves into the <span className="text-zinc-200">Active</span> filter. Workers pick jobs
            up with a short stagger so proxies are not rate-limited. Keep{" "}
            <span className="font-mono text-zinc-300">
              docker compose --profile full up -d redis api worker beat web
            </span>{" "}
            running on the server — without Beat, daily scrapes will not fire (laptop does not need to
            be on). Override with{" "}
            <span className="font-mono text-zinc-300">DAILY_SCRAPE_HOUR_IST</span> /{" "}
            <span className="font-mono text-zinc-300">DAILY_SCRAPE_MINUTE_IST</span>.
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
            <strong className="font-medium text-zinc-200">
              only posts dated on/after {PROGRAMME_STARTED_LABEL}
            </strong>{" "}
            through today (the programme window). Pre-programme posts are never included in Insights
            averages, totals, or ratios. We do not invent numbers — every average is a mean over that
            filtered set.
          </p>

          <h3 className="pt-1 text-sm font-semibold text-zinc-200">Mean (simple average)</h3>
          <Formula>mean(values) = sum(values) ÷ count(values)</Formula>
          <p className="text-sm text-zinc-400">If there are no programme-window posts, all averages are 0.</p>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">Avg likes</h3>
          <Formula>avg_likes = mean(likes of every programme-window post)</Formula>
          <Example title="Example">
            Posts in window: 100, 200, 50 likes → avg likes = (100 + 200 + 50) ÷ 3 = <strong>116.67</strong>
          </Example>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">Avg comments</h3>
          <Formula>avg_comments = mean(comments of every programme-window post)</Formula>
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
            Same ≥10 rule, but only on reel / video posts inside the programme window.
          </p>
          <Formula>avg_reel_views = mean(views of reels/videos where views ≥ 10)</Formula>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">Other derived fields</h3>
          <DataTable
            headers={["Metric", "How it is calculated"]}
            rows={[
              ["sampled_posts", "Count of posts with posted_at ≥ programme start (15 Jul 2026)"],
              ["total_likes_sampled", "Sum of likes across programme-window posts"],
              ["total_comments_sampled", "Sum of comments across programme-window posts"],
              ["total_views_sampled", "Sum of views only where views ≥ 10 (programme window)"],
              ["median_likes", "Middle value when programme likes are sorted"],
              ["max_likes / min_likes", "Highest / lowest likes in the programme window"],
              ["best / worst post", "Programme post with highest / lowest likes"],
              ["posts_last_7d / 30d", "Programme posts with posted_at in that lookback (floored at programme start)"],
              ["posting_frequency_per_week", "programme_posts ÷ (days from programme start → last post ÷ 7)"],
              ["like_follower_ratio", "(avg_likes ÷ followers) × 100 — 0 if followers = 0"],
              ["comment_follower_ratio", "(avg_comments ÷ followers) × 100 — 0 if followers = 0"],
              ["comments_to_likes_ratio", "(total comments ÷ total likes) × 100 — 0 if likes = 0"],
              ["video_share_pct", "% of programme posts that are video/reel"],
              ["image / reel / carousel counts", "Count by media_type in the programme window"],
              ["posts_count (IG)", "Instagram lifetime total — NOT programme-scoped"],
              ["highlight_reel_count", "Instagram profile field — NOT programme-scoped"],
            ]}
          />
          <p className="text-sm text-zinc-500">
            Posts without a recoverable date are excluded from the window (counted in{" "}
            <code className="rounded bg-white/[0.06] px-1 text-[12px]">posts_missing_dates</code>
            ). Profile-level IG totals (lifetime posts / highlights) are shown for context only.
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
            Leaderboard “overall” score is SPARK points from Instagram + YouTube content, combined
            audience growth, and judged/manual categories.{" "}
            <strong className="font-medium text-zinc-200">
              Data and points are calculated from {PROGRAMME_STARTED_LABEL} (programme start) through the selected /
              current date.
            </strong>{" "}
            Posts and milestones outside that window do not count. Crossposted Reels ↔ Shorts on the
            same day count once.
          </p>
          <ProgrammeWindowNote className="!text-xs" />
          <Formula>
            SPARK = consistency + min(performance, 3000) + growth + collabs + revenue + recognition +
            participation + monthly_bonuses
          </Formula>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">1) Weekly consistency (floor)</h3>
          <p className="text-sm text-zinc-400">
            <strong className="text-zinc-200">+10 pts per ISO week</strong> that meets the minimum
            (summed across the programme; capped at 660):
          </p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-zinc-300">
            <li>≥ 2 short-form pieces (Reels or YT Shorts ≤90s; crosspost counts once)</li>
            <li>≥ 1 long-form (≥3 min YouTube, or Instagram carousel)</li>
          </ul>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">2) Content performance (multiplier)</h3>
          <p className="text-sm text-zinc-400">Each piece scores from its view count (IG + YouTube):</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                Short / reel / Shorts bands
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
                Long-form / carousel bands
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
            Only the highest matching band applies per piece (not stacked). All piece points are
            summed, then capped at <strong className="text-zinc-200">3000</strong>.
          </p>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">3) Audience growth (milestones)</h3>
          <p className="text-sm text-zinc-400">
            Points for milestones <strong className="text-zinc-200">crossed inside the programme window</strong>.
            1k–30k use <strong className="text-zinc-200">combined IG + YouTube</strong> followers.
            50k requires a <strong className="text-zinc-200">single platform</strong> (+ GRIT).
          </p>
          <DataTable
            headers={["Followers ≥", "Points added"]}
            rows={[
              ["1,000 (combined)", "25"],
              ["5,000 (combined)", "75"],
              ["10,000 (combined)", "150"],
              ["20,000 (combined)", "300"],
              ["30,000 (combined)", "500"],
              ["50,000 (single platform)", "1,000 + GRIT"],
            ]}
          />
          <Example title="Example">
            Baseline 800 combined → end 12_000 combined unlocks 1k + 5k + 10k →{" "}
            <strong>250</strong> growth points.
          </Example>

          <h3 className="pt-2 text-sm font-semibold text-zinc-200">4–8) Judged / manual categories</h3>
          <p className="text-sm text-zinc-400">
            Collaborations, revenue, recognition, program participation, and monthly bonus challenges
            are awarded via admin insights (<code className="text-zinc-300">spark_points.*</code> or
            legacy <code className="text-zinc-300">spark_bonus_points</code>) and capped:
          </p>
          <DataTable
            headers={["Category", "Cap"]}
            rows={[
              ["Collaborations", "850"],
              ["Revenue", "3,000"],
              ["Recognition / features", "500"],
              ["Program participation", "470"],
              ["Monthly bonuses", "1,350"],
            ]}
          />

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
              ["Dashboard", "Overall + Today — metrics scored from 15 Jul 2026 onward"],
              ["Leaderboard", "Ranks / points / likes / views from cohort start → selected end date"],
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
            Dashboard <strong className="text-zinc-200">Overall → Scraped successfully</strong> counts
            each profile once (has IG card / last success). Re-scraping the same handle does not
            increase that number. <strong className="text-zinc-200">Today&apos;s data</strong> only
            counts successes and failures for the current UTC calendar day.
          </p>
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
