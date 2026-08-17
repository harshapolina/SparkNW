#!/usr/bin/env python3
"""Export roster students with valid IG that were missing from Mongo profiles."""

from datetime import datetime, timezone
import csv
import io
import re
import sys
from pathlib import Path

from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "python-shared"))

import importlib.util

from instascope_shared.domain.instagram import extract_username  # noqa: E402

_roster_path = ROOT / "packages" / "python-shared" / "instascope_shared" / "services" / "student_roster.py"
_spec = importlib.util.spec_from_file_location("student_roster", _roster_path)
_roster = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_roster)
map_sheet_row = _roster.map_sheet_row

OUT_PATH = ROOT / "data" / "missing_roster_profiles_172.csv"
# Profiles created on/after this UTC date were added by the bulk roster import fix.
IMPORT_CUTOFF = datetime(2026, 8, 17, tzinfo=timezone.utc)

INVALID_IG = {
    "",
    "nan",
    "none",
    "null",
    "-",
    ".",
    "na",
    "n/a",
    "nil",
    "invites",
    "no",
    "yes",
    "dont",
    "don't",
}
VALID_IG = re.compile(r"^[A-Za-z0-9._]{2,30}$")


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
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
        return text.lstrip("@").strip().lower().split("?")[0].split("/")[0]


def ig_valid(ig: str) -> bool:
    ig = (ig or "").lower()
    if ig in INVALID_IG or not VALID_IG.match(ig):
        return False
    if " " in ig or ig.startswith("not") or "account" in ig or "instagram" in ig:
        return False
    return True


def main() -> int:
    env = load_env(ROOT / ".env")
    db = MongoClient(env["MONGODB_URI"], serverSelectionTimeoutMS=20000)[env.get("MONGODB_DB") or "instascope"]

    db_sids: set[str] = set()
    db_igs: set[str] = set()
    for p in db["profiles"].find(
        {},
        {
            "username": 1,
            "student.student_id": 1,
            "student.instagram_username": 1,
            "student.instagram_handle": 1,
            "student.instagram_url": 1,
            "created_at": 1,
        },
    ):
        created = p.get("created_at")
        if created and created.replace(tzinfo=timezone.utc) >= IMPORT_CUTOFF:
            continue
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
                db_igs.add(ig)

    text = (ROOT / "data" / "spark_students.tsv").read_text(encoding="utf-8")
    rows = list(csv.reader(io.StringIO(text), delimiter="\t", quotechar='"'))
    headers = [h.strip() for h in rows[0]]

    seen_sid: dict[str, dict[str, str]] = {}
    for values in rows[1:]:
        if not any(str(v).strip() for v in values):
            continue
        mapped = map_sheet_row(headers, values)
        st = mapped["student"]
        sid = norm_sid(str(st.get("student_id") or ""))
        if not sid or sid in seen_sid:
            continue
        ig = ""
        if mapped.get("url"):
            try:
                ig = extract_username(mapped["url"])
            except Exception:
                ig = ""
        if not ig:
            ig = norm_ig(str(st.get("instagram_username") or st.get("instagram_handle") or ""))
        seen_sid[sid] = {
            "full_name": str(st.get("full_name") or ""),
            "student_id": sid,
            "instagram_username": ig,
            "instagram_url": str(st.get("instagram_url") or mapped.get("url") or ""),
            "email": str(st.get("email") or ""),
            "mobile": str(st.get("mobile") or ""),
            "university": str(st.get("university") or ""),
            "uid": str(st.get("uid") or ""),
            "duplicate_flag": str(st.get("duplicate_flag") or ""),
            "missing_info": str(st.get("missing_info") or ""),
        }

    missing: list[dict[str, str]] = []
    for r in seen_sid.values():
        sid = r["student_id"]
        ig = r["instagram_username"]
        if sid in db_sids:
            continue
        if not ig_valid(ig):
            continue
        if ig in db_igs:
            continue
        missing.append(r)

    missing.sort(key=lambda x: (x["student_id"], x["instagram_username"]))

    fieldnames = [
        "student_id",
        "instagram_username",
        "full_name",
        "email",
        "mobile",
        "university",
        "instagram_url",
        "uid",
        "duplicate_flag",
        "missing_info",
    ]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(missing)

    print(f"Wrote {len(missing)} rows to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
