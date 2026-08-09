# InstaScope

Enterprise Instagram profile monitoring — **MongoDB Atlas + FastAPI + Next.js + Celery**.

## SPARK (NIAT Creator Accelerator)

Dark student + admin portals live under `/spark`:

| Page | URL |
|------|-----|
| Student Dashboard | http://localhost:3001/spark/dashboard |
| Student Leaderboard | http://localhost:3001/spark/leaderboard |
| Admin Dashboard | http://localhost:3001/spark/admin |
| Admin Leaderboard | http://localhost:3001/spark/admin/leaderboard |

Ranking uses the SPARK point system (overall = total points). Sub-sorts: followers / views / engagement from scraped metrics (mock data until wired to InstaScope scrape).

## Running now

| Service | URL |
|---------|-----|
| Web UI | http://localhost:3001 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

### Login (already seeded via API test)

- Email: `harsh@instascope.dev`
- Password: `password123`

Or create a new account on `/signup`.

## Start commands (local)

```bash
# API + Redis (Docker)
docker compose up -d redis api

# Workers + Beat (required for automatic daily scrapes at 08:00 IST)
docker compose up -d worker beat
# Beat enqueues every ACTIVE profile each morning; worker scrapes them with stagger.

# Web (local)
cd apps/web
npm run dev
```

## Production (Hetzner — 24/7)

Live host: `62.238.57.52` · app dir: `/opt/instascope`

**All of these must stay up on the server** (laptop can be off):

| Service | Role |
|---------|------|
| `redis` | Celery broker |
| `api` | FastAPI + manual Add/Refresh |
| `worker` | Executes scrape jobs |
| `beat` | Schedules daily scrape at **08:00 IST** |
| `web` | Next.js UI (`:3000`) |

```bash
ssh root@62.238.57.52
cd /opt/instascope
bash scripts/deploy-hetzner.sh
# or:
# git pull origin main
# docker compose --profile full up -d --build redis api worker beat web
docker compose ps   # redis, api, worker, beat, web all Up
```

`restart: unless-stopped` keeps the stack running after reboot. Without **beat**, daily scrapes never fire.

## MongoDB

Uses your Atlas cluster via `.env` → `MONGODB_URI` (gitignored).

## Scraping (real Instagram data)

`LIVE_SCRAPE=1` is enabled. Add/Refresh pulls live public profile metrics and recent posts.

If Instagram blocks your IP (login wall), set a residential proxy:

```bash
SCRAPE_PROXY_URL=http://user:pass@host:port
```

Then recreate the API: `docker compose up -d --force-recreate api`


## Security

Rotate your Atlas DB password if it was shared in chat. Never commit `.env`.
