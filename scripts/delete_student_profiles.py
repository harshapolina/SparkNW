"""Remove student profiles and everything that hangs off them.

Dry-run by default: prints exactly what would go. Pass --apply to delete.

    python scripts/delete_student_profiles.py --profile-id <id> [--profile-id <id> ...]
    python scripts/delete_student_profiles.py --profile-id <id> --apply

Unlike the admin UI Delete (which only removes the profile document), this also
removes the profile's posts, snapshots, jobs, logs, notifications, YouTube data,
the student's login and that login's settings.

Student logins are matched by profile_id, or by admission number only when that
login is not attached to a profile that survives — so a student who still has
another profile keeps their login.

Note: Profile.user_id is the ADMIN who owns the profile, not the student.
Settings are therefore deleted for the student users found here, never for
profile.user_id.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]

RELATED = (
    "posts",
    "profile_snapshots",
    "jobs",
    "scrape_logs",
    "notifications",
    "youtube_channels",
    "youtube_videos",
    "youtube_snapshots",
)


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile-id", action="append", required=True, dest="ids")
    parser.add_argument("--apply", action="store_true", help="actually delete")
    args = parser.parse_args()

    _load_env()
    db = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=20000)[
        os.environ.get("MONGODB_DB", "instascope")
    ]

    try:
        oids = [ObjectId(i) for i in args.ids]
    except Exception as exc:  # noqa: BLE001
        print(f"invalid profile id: {exc}")
        return 2

    profiles = list(db.profiles.find({"_id": {"$in": oids}}))
    found = {str(p["_id"]) for p in profiles}
    missing = [i for i in args.ids if i not in found]
    if missing:
        print(f"not found (nothing to do for these): {missing}")
    if not profiles:
        return 1

    pids = sorted(found)
    sids = sorted(
        {
            str((p.get("student") or {}).get("student_id") or "").strip()
            for p in profiles
        }
        - {""}
    )

    print(f"profiles to remove: {len(profiles)}")
    for p in profiles:
        s = p.get("student") or {}
        name = str(s.get("full_name") or p.get("full_name") or "").encode("ascii", "replace").decode()
        print(f"  {p['_id']}  @{p.get('username')}  student_id={s.get('student_id')}  name={name}")

    # A student login is removable when it points at a doomed profile, or it
    # carries the admission number and is not attached to a surviving profile.
    candidates = list(
        db.users.find(
            {
                "role": "student",
                "$or": [{"profile_id": {"$in": pids}}, {"student_id": {"$in": sids}}],
            }
        )
    )
    users = [
        u
        for u in candidates
        if (u.get("profile_id") in pids) or not u.get("profile_id")
    ]
    kept = [u for u in candidates if u not in users]
    uids = [str(u["_id"]) for u in users]

    plan: dict[str, int] = {"profiles": len(profiles)}
    for coll in RELATED:
        plan[coll] = db[coll].count_documents({"profile_id": {"$in": pids}})
    plan["student_users"] = len(users)
    plan["user_settings"] = db.user_settings.count_documents({"user_id": {"$in": uids}}) if uids else 0

    print("\nwould delete:" if not args.apply else "\ndeleting:")
    for k, v in plan.items():
        print(f"  {k:18s} {v}")
    if kept:
        print(
            "\nkeeping student logins attached to other profiles: "
            + ", ".join(f"{u['_id']}->{u.get('profile_id')}" for u in kept)
        )

    if not args.apply:
        print("\ndry-run only. re-run with --apply to delete.")
        return 0

    done: dict[str, int] = {}
    for coll in RELATED:
        done[coll] = db[coll].delete_many({"profile_id": {"$in": pids}}).deleted_count
    if uids:
        done["user_settings"] = db.user_settings.delete_many({"user_id": {"$in": uids}}).deleted_count
        done["student_users"] = db.users.delete_many(
            {"_id": {"$in": [ObjectId(u) for u in uids]}}
        ).deleted_count
    done["profiles"] = db.profiles.delete_many({"_id": {"$in": oids}}).deleted_count
    print("\ndeleted:", done)
    print("The public Top 10 snapshot rebuilds on its own within a few minutes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
