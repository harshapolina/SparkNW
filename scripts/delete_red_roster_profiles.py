"""Delete roster rows flagged red (NIAT ID + IG handle). Related docs included."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

root = Path(__file__).resolve().parents[1]
env_path = root / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

STUDENT_IDS = [
    "N25H03A0864",
    "N25H01A1076",
    "N25N01A0122",
    "N25H03A0139",
    "262921040",
    "N25C02A0028",
    "BSA202611629",
    "2102508581",
    "N25H03A1025",
    "N25H01A0843",
    "N25H03A0552",
    "N25H01A1356",
    "NIATZ7A0007",
    "N25N01A0167",
    "N25N01A0308",
]

HANDLES = [
    "lensofbhanu",
    "iskcon_nizamabad",
    "mayankkontey",
    "battu_universe",
    "sarv.lfe",
    "gohub2026",
    "only_softcuts",
    "voicethroughkannada",
    "niat.creatorlab",
    "sayefx_",
    "fear.xff",
    "srushanth0973",
    "niat_giri",
    "_anmol_thakral_18",
    "buttergarlicnaanwithdalmakhni",
]


def main() -> None:
    apply = "--apply" in sys.argv
    uri = os.environ["MONGODB_URI"]
    db_name = os.environ.get("MONGODB_DB", "instascope")
    client = MongoClient(uri, serverSelectionTimeoutMS=20000)
    db = client[db_name]
    profiles = db["profiles"]

    handle_lc = [h.lower().lstrip("@") for h in HANDLES]
    found = list(
        profiles.find(
            {
                "$or": [
                    {"student.student_id": {"$in": STUDENT_IDS}},
                    {"username": {"$in": handle_lc}},
                    {"username": {"$in": HANDLES}},
                ]
            },
            {"username": 1, "full_name": 1, "student": 1, "user_id": 1},
        )
    )

    print(f"matched {len(found)} profile(s)")
    for p in found:
        sid = (p.get("student") or {}).get("student_id")
        name = str(p.get("full_name") or "").encode("ascii", "replace").decode("ascii")
        print(f"  {p.get('_id')}  @{p.get('username')}  student_id={sid}  name={name}")

    if not apply:
        print("dry-run only. re-run with --apply to delete.")
        return

    pids = [str(p["_id"]) for p in found]
    uids = [str(p.get("user_id")) for p in found if p.get("user_id")]
    oid_list = []
    for p in found:
        _id = p["_id"]
        oid_list.append(_id)

    deleted = {}
    deleted["profiles"] = profiles.delete_many({"_id": {"$in": oid_list}}).deleted_count
    for coll in (
        "posts",
        "profile_snapshots",
        "jobs",
        "scrape_logs",
        "notifications",
        "youtube_channels",
        "youtube_videos",
        "youtube_snapshots",
    ):
        deleted[coll] = db[coll].delete_many({"profile_id": {"$in": pids}}).deleted_count

    student_users = db["users"].delete_many(
        {
            "role": "student",
            "$or": [
                {"profile_id": {"$in": pids}},
                {"student_id": {"$in": STUDENT_IDS}},
            ],
        }
    ).deleted_count
    deleted["student_users"] = student_users
    if uids:
        deleted["user_settings"] = db["user_settings"].delete_many(
            {"user_id": {"$in": uids}}
        ).deleted_count

    print("deleted:", deleted)


if __name__ == "__main__":
    main()
