#!/usr/bin/env python3
"""Import roster Instagram handles missing from Mongo, then queue scrapes.

- Skip anyone already in profiles (any status: active/failed/paused/unavailable/private).
- Upsert only truly missing rows with valid IG usernames.
- Queue bulk scrape so results land in Active / Private / Failed / Missing accordingly.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient, UpdateOne

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "python-shared"))

import importlib.util

_roster_path = ROOT / "packages" / "python-shared" / "instascope_shared" / "services" / "student_roster.py"
_spec = importlib.util.spec_from_file_location("student_roster", _roster_path)
_roster = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_roster)
map_sheet_row = _roster.map_sheet_row
merge_student = _roster.merge_student

from instascope_shared.domain.instagram import extract_username  # noqa: E402

ADMIN_EMAIL = "sparkadmin@nw.co.in"
ADMIN_PASSWORD = "Editco@spark3"

INVALID_IG = {
    "",
    "nan",
    "none",
    "null",
    "-",
    ".",
    "./",
    "na",
    "n/a",
    "nil",
    "invites",
    "no",
    "yes",
    "dont",
    "don't",
    "nl",
    "https:",
}
VALID_IG = re.compile(r"^[A-Za-z0-9._]{2,30}$")


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def norm_sid(raw: str) -> str:
    return re.sub(r"\s+", "", (raw or "").strip().upper())


def norm_ig(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        return extract_username(text)
    except Exception:
        t = text.lstrip("@").strip().lower()
        return t.split("?")[0].split("/")[0]


def ig_valid(ig: str) -> bool:
    ig = (ig or "").lower()
    if ig in INVALID_IG or not VALID_IG.match(ig):
        return False
    if set(ig) <= {".", "_"}:
        return False
    if " " in ig or ig.startswith("not") or "account" in ig or "instagram" in ig:
        return False
    if "create" in ig or "start" in ig or "suspend" in ig:
        return False
    return True


def http_json(method: str, url: str, body: dict | None = None, token: str | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {detail}") from e


def login(api: str) -> str:
    res = http_json("POST", f"{api}/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if isinstance(res, dict):
        if res.get("access_token"):
            return res["access_token"]
        tokens = res.get("tokens") or {}
        if tokens.get("access_token"):
            return tokens["access_token"]
    raise RuntimeError(f"login failed: {res}")


def load_roster(tsv: Path) -> list[dict]:
    text = tsv.read_text(encoding="utf-8")
    rows = list(csv.reader(io.StringIO(text), delimiter="\t", quotechar='"'))
    if not rows:
        return []
    headers = [h.strip() for h in rows[0]]
    out: list[dict] = []
    seen_ig: set[str] = set()
    for values in rows[1:]:
        if not any(str(v).strip() for v in values):
            continue
        mapped = map_sheet_row(headers, values)
        st = mapped["student"]
        sid = norm_sid(str(st.get("student_id") or ""))
        ig = ""
        if mapped.get("url"):
            try:
                ig = extract_username(mapped["url"])
            except Exception:
                ig = ""
        if not ig:
            ig = norm_ig(str(st.get("instagram_username") or st.get("instagram_handle") or ""))
        if not ig_valid(ig):
            continue
        key = ig.lower()
        if key in seen_ig:
            continue
        seen_ig.add(key)
        out.append(
            {
                "username": key,
                "url": f"https://www.instagram.com/{key}",
                "student": merge_student({}, st),
                "student_id": sid,
            }
        )
    return out


def resolve_admin(db) -> dict:
    user = db.users.find_one({"email": re.compile(f"^{re.escape(ADMIN_EMAIL)}$", re.I)})
    if user:
        return user
    top = list(
        db.profiles.aggregate(
            [
                {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
                {"$sort": {"n": -1}},
                {"$limit": 1},
            ]
        )
    )
    if top and top[0].get("_id"):
        oid = top[0]["_id"]
        try:
            user = db.users.find_one({"_id": ObjectId(str(oid))})
        except Exception:
            user = db.users.find_one({"_id": oid})
    if not user:
        raise RuntimeError(f"Admin user {ADMIN_EMAIL} not found")
    return user


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", default=str(ROOT / "data" / "spark_students.tsv"))
    ap.add_argument("--api", default="http://62.238.57.52:8000/api/v1")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-scrape", action="store_true", help="Import only; do not queue scrapes")
    ap.add_argument("--limit", type=int, default=0, help="Max missing profiles to import/scrape")
    ap.add_argument("--chunk", type=int, default=40, help="Bulk refresh chunk size")
    args = ap.parse_args()

    env = load_dotenv(ROOT / ".env")
    uri = os.environ.get("MONGODB_URI") or env.get("MONGODB_URI")
    db_name = os.environ.get("MONGODB_DB") or env.get("MONGODB_DB") or "instascope"
    if not uri:
        print("MONGODB_URI missing", file=sys.stderr)
        return 1

    roster = load_roster(Path(args.tsv))
    print(f"Roster with valid IG usernames: {len(roster)}")

    client = MongoClient(uri, serverSelectionTimeoutMS=20000)
    db = client[db_name]
    admin = resolve_admin(db)
    user_id = str(admin["_id"])
    print(f"Admin user_id={user_id} email={admin.get('email')}")
    print(f"Live profiles count: {db.profiles.estimated_document_count()}")

    db_sids: set[str] = set()
    db_igs: set[str] = set()
    status_counts: dict[str, int] = {}
    for p in db.profiles.find(
        {},
        {
            "username": 1,
            "status": 1,
            "is_private": 1,
            "student.student_id": 1,
            "student.instagram_username": 1,
            "student.instagram_handle": 1,
            "student.instagram_url": 1,
        },
    ):
        st = p.get("status") or "unknown"
        if p.get("is_private"):
            st = f"{st}+private"
        status_counts[st] = status_counts.get(st, 0) + 1
        s = p.get("student") or {}
        sid = norm_sid(str(s.get("student_id") or ""))
        if sid:
            db_sids.add(sid)
        for cand in [
            p.get("username"),
            s.get("instagram_username"),
            s.get("instagram_handle"),
            s.get("instagram_url"),
        ]:
            ig = norm_ig(str(cand or ""))
            if ig:
                db_igs.add(ig.lower())

    print("DB status mix:", dict(sorted(status_counts.items())))

    already: list[dict] = []
    missing: list[dict] = []
    for row in roster:
        ig = row["username"]
        sid = row["student_id"]
        if ig in db_igs or (sid and sid in db_sids):
            already.append(row)
        else:
            missing.append(row)

    print(f"Already in DB (any filter): {len(already)} — skip")
    print(f"Truly missing (will import): {len(missing)}")

    if args.limit and args.limit > 0:
        missing = missing[: args.limit]
        print(f"Limited to {len(missing)}")

    report = ROOT / "data" / "missing_to_import_now.csv"
    with report.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["student_id", "instagram_username", "full_name", "university"])
        w.writeheader()
        for r in missing:
            st = r["student"]
            w.writerow(
                {
                    "student_id": r["student_id"],
                    "instagram_username": r["username"],
                    "full_name": st.get("full_name") or "",
                    "university": st.get("university") or "",
                }
            )
    print(f"Wrote {report}")

    if args.dry_run:
        for r in missing[:25]:
            print(f"  would import @{r['username']}  {r['student'].get('full_name')}  {r['student_id']}")
        if len(missing) > 25:
            print(f"  ... and {len(missing) - 25} more")
        return 0

    if not missing:
        print("Nothing to import.")
        return 0

    now = datetime.now(timezone.utc)
    ops: list[UpdateOne] = []
    usernames = [r["username"] for r in missing]
    for r in missing:
        student = merge_student({}, r["student"])
        ops.append(
            UpdateOne(
                {"user_id": user_id, "username": r["username"]},
                [
                    {
                        "$set": {
                            "user_id": user_id,
                            "org_id": {"$ifNull": ["$org_id", "spark"]},
                            "username": r["username"],
                            "profile_url": r["url"],
                            "full_name": {"$ifNull": ["$full_name", student.get("full_name") or None]},
                            "updated_at": now,
                            "student": {
                                "$mergeObjects": [
                                    {"$ifNull": ["$student", {}]},
                                    student,
                                ]
                            },
                            "followers": {"$ifNull": ["$followers", 0]},
                            "following": {"$ifNull": ["$following", 0]},
                            "posts_count": {"$ifNull": ["$posts_count", 0]},
                            "avg_likes": {"$ifNull": ["$avg_likes", 0.0]},
                            "avg_views": {"$ifNull": ["$avg_views", 0.0]},
                            "avg_comments": {"$ifNull": ["$avg_comments", 0.0]},
                            "engagement_rate": {"$ifNull": ["$engagement_rate", 0.0]},
                            "growth_pct_today": {"$ifNull": ["$growth_pct_today", 0.0]},
                            "is_private": {"$ifNull": ["$is_private", False]},
                            "is_business": {"$ifNull": ["$is_business", False]},
                            "is_verified": {"$ifNull": ["$is_verified", False]},
                            "highlight_reel_count": {"$ifNull": ["$highlight_reel_count", 0]},
                            "follower_following_ratio": {"$ifNull": ["$follower_following_ratio", 0.0]},
                            "insights": {"$ifNull": ["$insights", {}]},
                            "status": {"$ifNull": ["$status", "active"]},
                            "created_at": {"$ifNull": ["$created_at", now]},
                        }
                    }
                ],
                upsert=True,
            )
        )

    result = db.profiles.bulk_write(ops, ordered=False)
    print(
        f"Mongo upsert: matched={result.matched_count} "
        f"modified={result.modified_count} upserted={len(result.upserted_ids)}"
    )

    docs = list(
        db.profiles.find(
            {"user_id": user_id, "username": {"$in": usernames}},
            {"_id": 1, "username": 1, "status": 1, "is_private": 1, "last_success_at": 1},
        )
    )
    print(f"Profiles ready for scrape: {len(docs)}")

    if args.no_scrape:
        print("Skipping scrape (--no-scrape)")
        return 0

    token = login(args.api)
    ids = [str(d["_id"]) for d in docs]
    chunk = max(1, args.chunk)
    ok = fail = 0
    for i in range(0, len(ids), chunk):
        batch = ids[i : i + chunk]
        try:
            http_json("POST", f"{args.api}/profiles/bulk/refresh", {"ids": batch}, token=token)
            ok += len(batch)
            print(f"  queued bulk refresh {i + 1}-{i + len(batch)} / {len(ids)}", flush=True)
        except RuntimeError as e:
            fail += len(batch)
            print(f"  bulk refresh FAILED: {e}", file=sys.stderr, flush=True)
            if "401" in str(e) or "403" in str(e):
                try:
                    token = login(args.api)
                except Exception:
                    pass
            # fallback: single refresh
            for pid in batch:
                try:
                    http_json("POST", f"{args.api}/profiles/{pid}/refresh", token=token)
                    ok += 1
                    fail -= 1
                except RuntimeError as e2:
                    print(f"    single refresh fail {pid}: {e2}", file=sys.stderr, flush=True)

    print(f"Scrape queue done: queued_ok≈{ok} fail≈{fail}")
    print("After scrape finishes, private→Private filter, errors→Failed/Missing, success→Active.")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
