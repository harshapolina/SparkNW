# YouTube Data API v3 (SPARK)

Public-data tracking only (no OAuth / Analytics). Instagram scrape paths are unchanged.

## Configure the API key

Set **server-side only** (never `NEXT_PUBLIC_*`, never commit):

```bash
# local or production .env
YOUTUBE_API_KEY=your_key_here
```

Docker Compose loads `.env` via `env_file` for `api`, `worker`, and `beat`.  
Do **not** add `YOUTUBE_API_KEY: ${YOUTUBE_API_KEY:-}` under `environment:` (empty defaults wipe the key).

## Test ONE channel (no bulk)

```bash
# Resolve only (prints public metrics; no Mongo write)
python scripts/test_youtube_channel.py --url "https://www.youtube.com/@GoogleDevelopers" --resolve-only

# Connect + sync into a Profile (requires Mongo)
python scripts/test_youtube_channel.py --profile-id "<PROFILE_OBJECT_ID>" --url "@SomeCreator" --max-videos 10
```

Admin API (JWT required):

- `POST /api/v1/youtube/resolve` — resolve without DB write  
- `POST /api/v1/youtube/profiles/{id}/connect` — resolve, store `channel_id`, sync  
- `POST /api/v1/youtube/profiles/{id}/sync` — re-sync using stored id (no `search.list`)  
- `GET /api/v1/youtube/profiles/{id}` — linked channel status  

## Daily scheduler

Celery Beat entry `daily-youtube-sync` at 08:00 IST by default (`DAILY_YOUTUBE_SYNC_HOUR_IST` / `MINUTE`).  

**Own admin toggle** (independent of Instagram daily scrape):

- `GET/PATCH /api/v1/settings/daily-youtube-sync` `{ "enabled": true|false }`  
- Default when unset: **off** (quota-safe until you enable)

## Endpoints used

| Call | Use | Approx quota |
|------|-----|--------------|
| `channels.list` (`id` / `forHandle` / `forUsername`) | Resolve + daily channel stats | 1 / call |
| `playlistItems.list` | Uploads playlist pages | 1 / page |
| `videos.list` | Batched video stats (≤50 ids) | 1 / call |
| `search.list` | **Last resort** one-time `/c/CustomName` resolve only | 100 |

Daily sync uses stored `channel_id` only.

## Collections

- `youtube_channels`  
- `youtube_videos`  
- `youtube_snapshots`  

`profiles` only stores `youtube_channel_id`, `youtube_connected`, `youtube_last_synced_at`.

## Video window

Sync pulls **all public uploads on/after programme start** (`SPARK_COHORT_START`, default **2026-07-15**).
Older uploads are not stored. `max_videos: 0` (default) means every in-window upload (no soft cap).

Each sync requests **all public Data API parts** for channels + videos and stores the full `public_api` payload
(plus flattened fields). Private Analytics / comment threads are not included (API key / quota limits).

Insights: `GET /api/v1/youtube/profiles/{id}/insights` — channel public fields + every stored video’s public Data API fields for that window (Admin → Scraping → profile → Insights → YouTube insights).

Videos are classified as **Shorts** (duration ≤ 180s or `#shorts` in title/description/tags) vs **long-form**; counts and lists are segregated in Insights.

## Scoring

`YOUTUBE_SCORING_ENABLED` / `youtube_scoring_enabled` defaults to **false**.  
Leaderboard shows YT metrics for display only; Instagram SPARK points are unchanged until a formula is provided.

