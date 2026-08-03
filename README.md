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

## Start commands

```bash
# API + Redis (Docker)
docker compose up -d redis api

# Optional daily workers
docker compose up -d worker beat

# Web (local)
cd apps/web
npm run dev
```

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
