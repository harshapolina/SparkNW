#!/usr/bin/env python3
"""Import SPARK registration TSV into InstaScope (create admin + bulk import).

Usage:
  python scripts/import_spark_roster.py --api http://62.238.57.52:8000/api/v1 \\
    --tsv data/spark_students.tsv --scrape

  python scripts/import_spark_roster.py --api http://localhost:8000/api/v1 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Load student_roster without importing the full services package (avoids beanie etc.)
import importlib.util

_roster_path = ROOT / "packages" / "python-shared" / "instascope_shared" / "services" / "student_roster.py"
_spec = importlib.util.spec_from_file_location("student_roster", _roster_path)
_roster = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
# Provide a minimal extract_username stub if domain import fails
sys.path.insert(0, str(ROOT / "packages" / "python-shared"))
_spec.loader.exec_module(_roster)
map_sheet_row = _roster.map_sheet_row

ADMIN_EMAIL = "sparkadmin@NW.co.in"
ADMIN_PASSWORD = "Editco@spark3"
ADMIN_NAME = "Spark Admin"


def http_json(method: str, url: str, body: dict | None = None, token: str | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {detail}") from e


def ensure_admin(api: str) -> str:
    """Signup or login; return access token."""
    try:
        res = http_json(
            "POST",
            f"{api}/auth/signup",
            {
                "name": ADMIN_NAME,
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD,
            },
        )
        print(f"Created admin {ADMIN_EMAIL}")
        return _token_from_auth(res)
    except RuntimeError as e:
        if "409" not in str(e) and "already" not in str(e).lower() and "exist" not in str(e).lower():
            # try login anyway
            pass
        res = http_json(
            "POST",
            f"{api}/auth/login",
            {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        print(f"Logged in as {ADMIN_EMAIL}")
        return _token_from_auth(res)


def _token_from_auth(res: dict) -> str:
    if res.get("access_token"):
        return res["access_token"]
    tokens = res.get("tokens") or {}
    if tokens.get("access_token"):
        return tokens["access_token"]
    raise RuntimeError(f"No access_token in auth response: {list(res.keys())}")


def load_tsv(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    # Drop trailing junk after empty rows of mostly tabs
    reader = csv.reader(io.StringIO(text), delimiter="\t", quotechar='"')
    rows = list(reader)
    if not rows:
        return []
    headers = [h.strip() for h in rows[0]]
    out: list[dict] = []
    seen: set[str] = set()
    for values in rows[1:]:
        if not any(str(v).strip() for v in values):
            continue
        mapped = map_sheet_row(headers, values)
        url = mapped["url"]
        student = mapped["student"]
        if not url:
            continue
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"url": url, "student": student})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://62.238.57.52:8000/api/v1")
    ap.add_argument("--tsv", default=str(ROOT / "data" / "spark_students.tsv"))
    ap.add_argument("--chunk", type=int, default=40)
    ap.add_argument("--scrape", action="store_true", help="Trigger live scrapes during import")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-admin", action="store_true")
    args = ap.parse_args()

    path = Path(args.tsv)
    if not path.exists():
        print(f"Missing TSV: {path}", file=sys.stderr)
        return 1

    rows = load_tsv(path)
    print(f"Parsed {len(rows)} profiles with Instagram URLs from {path}")
    if not rows:
        return 1
    print("Sample:", rows[0]["url"], rows[0]["student"].get("full_name"))

    if args.dry_run:
        unis = {}
        for r in rows:
            u = r["student"].get("university") or "?"
            unis[u] = unis.get(u, 0) + 1
        print("Top universities:", sorted(unis.items(), key=lambda x: -x[1])[:10])
        return 0

    token = None if args.skip_admin else ensure_admin(args.api.rstrip("/"))
    if token is None:
        print("Need auth token", file=sys.stderr)
        return 1

    api = args.api.rstrip("/")
    total_imported = total_updated = total_skipped = total_failed = 0
    for i in range(0, len(rows), args.chunk):
        chunk = rows[i : i + args.chunk]
        print(f"Importing {i + 1}-{i + len(chunk)} / {len(rows)} …")
        res = http_json(
            "POST",
            f"{api}/profiles/bulk/import",
            {"rows": chunk, "scrape_now": bool(args.scrape)},
            token=token,
        )
        total_imported += res.get("imported", 0)
        total_updated += res.get("updated", 0)
        total_skipped += res.get("skipped", 0)
        total_failed += res.get("failed", 0)
        print(
            f"  + imported={res.get('imported')} updated={res.get('updated')} "
            f"skipped={res.get('skipped')} failed={res.get('failed')} scraping={res.get('scraping')}"
        )
        time.sleep(0.3)

    print(
        f"Done. imported={total_imported} updated={total_updated} "
        f"skipped={total_skipped} failed={total_failed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
