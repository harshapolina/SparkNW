"""Regenerate spark-top50 canvas with NIAT ID + IG/YT links."""
from __future__ import annotations

import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
data = json.loads((root / "scripts" / "top50_leaderboard.json").read_text(encoding="utf-8"))
rows = data["top50"]

canvas_path = Path.home() / ".cursor" / "projects" / "c-Users-harsh-OneDrive-Desktop-EDITCO-INSTASCOPE" / "canvases" / "spark-top50-leaderboard.canvas.tsx"


def esc(s: str | None) -> str:
    if s is None:
        return ""
    return (
        str(s)
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
    )


def clean_yt(url: str | None) -> str | None:
    if not url or url.strip() in {"--", "-", "n/a", "N/A", "null"}:
        return None
    return url.strip()


items = []
for r in rows:
    yt = clean_yt(r.get("youtube_url"))
    items.append(
        {
            "rank": r["rank"],
            "username": r["username"],
            "name": r.get("name") or r["username"],
            "student_id": r.get("student_id") or "",
            "campus": r.get("campus") or "—",
            "points": r["points"],
            "consistency": r.get("consistency") or 0,
            "performance": r.get("performance") or 0,
            "growth": r.get("growth") or 0,
            "followers": r.get("followers") or 0,
            "yt": r.get("youtube_subscribers"),
            "instagram_url": r.get("instagram_url")
            or f"https://www.instagram.com/{r['username']}/",
            "youtube_url": yt,
        }
    )

# compact TS object literals
lines = []
for it in items:
    yt_js = "null" if it["youtube_url"] is None else json.dumps(it["youtube_url"])
    yt_subs = "null" if it["yt"] is None else str(int(it["yt"]))
    lines.append(
        "  {"
        f' rank: {it["rank"]},'
        f' username: {json.dumps(it["username"])},'
        f' name: {json.dumps(it["name"])},'
        f' studentId: {json.dumps(it["student_id"])},'
        f' campus: {json.dumps(it["campus"])},'
        f' points: {it["points"]},'
        f' consistency: {it["consistency"]},'
        f' performance: {it["performance"]},'
        f' growth: {it["growth"]},'
        f' followers: {it["followers"]},'
        f' yt: {yt_subs},'
        f' igUrl: {json.dumps(it["instagram_url"])},'
        f' ytUrl: {yt_js},'
        " },"
    )

body = "\n".join(lines)

tsx = f'''import {{ Card, CardBody, CardHeader, H1, H2, Link, Stack, Stat, Table, Text }} from "cursor/canvas";

const META = {{
  totalCreators: {data.get("total_creators", 503)},
  windowFrom: {json.dumps(data.get("window_from"))},
  windowTo: {json.dumps(data.get("window_to"))},
  generatedAt: {json.dumps(data.get("generated_at"))},
}};

const TOP50 = [
{body}
] as const;

function fmt(n: number | null | undefined) {{
  if (n == null) return "—";
  return n.toLocaleString("en-IN");
}}

export default function Top50LeaderboardCanvas() {{
  const top = TOP50[0];
  const withYt = TOP50.filter((r) => r.ytUrl).length;

  return (
    <Stack gap={{20}} style={{{{ padding: 24 }}}}>
      <Stack gap={{6}}>
        <H1>SPARK overall leaderboard — Top 50</H1>
        <Text tone="secondary" size="small">
          Source: MongoDB Atlas · SPARK points (IG + YouTube) · window {{META.windowFrom}} →{{" "}}
          {{META.windowTo}} · {{META.totalCreators}} creators · includes NIAT ID + IG/YT links
        </Text>
      </Stack>

      <div
        style={{{{
          display: "grid",
          gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
          gap: 12,
        }}}}
      >
        <Stat label="Creators scored" value={{String(META.totalCreators)}} />
        <Stat label="#1 points" value={{fmt(top.points)}} />
        <Stat label="#1 NIAT ID" value={{top.studentId || "—"}} />
        <Stat label="Top50 with YT link" value={{`${{withYt}} / 50`}} />
      </div>

      <Card>
        <CardHeader
          trailing={{
            <Text size="small" tone="secondary">
              Links open Instagram / YouTube profiles
            </Text>
          }}
        >
          Top 50 by SPARK points
        </CardHeader>
        <CardBody style={{{{ padding: 0 }}}}>
          <Table
            stickyHeader
            striped
            headers={{[
              "#",
              "NIAT ID",
              "Handle",
              "Name",
              "Campus",
              "Points",
              "Cons",
              "Perf",
              "Growth",
              "IG",
              "YouTube",
              "IG fol",
              "YT subs",
            ]}}
            columnAlign={{[
              "right",
              "left",
              "left",
              "left",
              "left",
              "right",
              "right",
              "right",
              "right",
              "left",
              "left",
              "right",
              "right",
            ]}}
            rows={{TOP50.map((r) => [
              String(r.rank),
              r.studentId || "—",
              `@${{r.username}}`,
              r.name,
              r.campus,
              fmt(r.points),
              String(r.consistency),
              String(r.performance),
              String(r.growth),
              <Link href={{r.igUrl}}>Instagram</Link>,
              r.ytUrl ? <Link href={{r.ytUrl}}>YouTube</Link> : "—",
              fmt(r.followers),
              r.yt == null ? "—" : fmt(r.yt),
            ])}}
          />
        </CardBody>
      </Card>

      <Stack gap={{4}}>
        <H2>Notes</H2>
        <Text size="small" tone="secondary">
          NIAT ID from roster student.student_id. Instagram = profile URL. YouTube = connected
          channel URL / roster youtube_link when available. Growth near-zero means no audience
          milestones crossed inside the programme window yet.
        </Text>
      </Stack>
    </Stack>
  );
}}
'''

canvas_path.write_text(tsx, encoding="utf-8")
print("wrote", canvas_path)
print("rows", len(items), "with yt", sum(1 for i in items if i["youtube_url"]))
