# InstaScope MongoDB schema

> Database: **MongoDB** (Atlas or self-hosted). Connection via `MONGODB_URI`.

## Why MongoDB (for this product)

- Scrape results are naturally document-shaped (profile + posts batch).
- Horizontal scale via sharding on `user_id` / `profile_id` later.
- Flexible fields for Instagram payload changes without rigid migrations.
- Still **normalized into separate collections** — never one giant blob as source of truth.

## Collections

| Collection | Purpose | Uniqueness |
|---|---|---|
| `users` | Auth identity | `email` |
| `user_settings` | Thresholds, dark mode, timezone | `user_id` |
| `profiles` | Tracked IG accounts + **cached** current metrics | `(user_id, username)` |
| `posts` | Latest known posts (upsert by IG id) | `ig_post_id` |
| `profile_snapshots` | **Immutable** daily metrics for charts | `(profile_id, snapshot_date)` |
| `jobs` | Scrape / refresh job state | — |
| `scrape_logs` | Diagnostics per attempt | — |
| `notifications` | User-facing alerts | — |

## Normalization rules

1. Historical follower counts live only in `profile_snapshots`.
2. `profiles.followers` is a cache updated after successful scrape — charts never rely on it alone.
3. Posts are upserted; do not duplicate the same `ig_post_id`.
4. Jobs reference `profile_id` by string id — no embedded scrape HTML.

## Indexes (critical for 1M profiles)

- `profiles`: `(user_id, username)`, `(status, last_scraped_at)`
- `profile_snapshots`: `(profile_id, snapshot_date)`, `(user_id, snapshot_date)`
- `posts`: `(profile_id, posted_at desc)`
- `jobs`: `(status, scheduled_at)`
- `notifications`: `(user_id, is_read, created_at desc)`

## Env

```bash
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=instascope
```

Paste your Atlas (or local) URI into `.env` — the app reads it on boot.
