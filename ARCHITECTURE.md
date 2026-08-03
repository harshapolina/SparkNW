# InstaScope — Architecture

> Phase 1 deliverable. No feature code yet. This document explains **why** the system is shaped this way so it can grow from ~900 profiles/day to 1,000,000 monitored profiles and millions of historical rows.

---

## Product thesis

InstaScope is a **continuous monitoring platform**, not a one-shot scraper UI.

The core loop is:

```
User adds profile URL → Profile stored → Daily scheduler enqueues jobs
→ Workers scrape via Playwright → Snapshots + posts persist → Analytics derive
→ Notifications fire on thresholds → Dashboard reads precomputed metrics
```

Everything in the codebase is organized around that loop.

---

## Why this architecture (not a monolith CRUD app)

| Decision | Choice | Why |
|---|---|---|
| Repo layout | **Monorepo** (`apps/`, `packages/`, `infra/`) | One product, many runtimes. Shared contracts (OpenAPI types, env conventions) without publishing private npm/pypi packages on day one. |
| Frontend | **Next.js App Router + TanStack Query** | Server components for shell/SEO-auth gates; client for charts/tables. Query handles cache, stale data, optimistic bulk ops. |
| API | **FastAPI** | Async I/O, OpenAPI-first contracts, typed Pydantic models — the UI never invents shapes. |
| ODM | **Beanie (Motor / async MongoDB)** | Python workers and API share the same document models. Async-native with FastAPI. |
| Queue | **Redis + Celery** | Scraping is slow, flaky, and must scale horizontally. API returns `202` + job id; workers own retries/backoff. |
| Scraper | **Playwright in isolated workers** | Browser automation must not live inside request handlers. Isolation lets us restart scraper pods without killing the API. |
| DB | **MongoDB** (Atlas or self-hosted) | Document model fits scrape payloads; compound indexes + time-series-friendly snapshot collection for history at scale. |
| Analytics | **Precomputed fields + snapshot collection** | Never aggregate raw posts on every dashboard load. Update cached metrics on scrape completion. |
| Auth | **JWT + refresh cookies** | Stateless API scale-out; refresh rotation for security without sticky sessions. |

### What we explicitly reject

- **Scrape-inside-API-request** — timeouts, browser leaks, no retry fairness.
- **Denormalized “profile blob” JSON as source of truth** — kills analytics and history.
- **One Celery task that scrapes all 900 profiles** — no parallelism, one failure kills the batch.
- **Charts reading raw `posts` every page load** — dies at scale; use daily metrics tables.
- **Bootstrap / generic admin CRUD** — product is the UI; charts and density are first-class.

---

## Scale model (design targets)

| Dimension | Day-1 | Target |
|---|---|---|
| Profiles monitored | ~900 | 1,000,000 |
| Snapshots | 900/day | 1M/day |
| Posts stored | tens of thousands | hundreds of millions |
| Concurrent scrape workers | 2–4 | 50–200 (autoscale on queue depth) |
| API replicas | 1 | N behind LB |

### Throughput math (900/day → 1M/day)

- At 900 profiles/day with ~20s scrape+write: ~5 worker-hours/day → trivial on 2 workers.
- At 1M/day with 30s average: ~8,333 worker-hours/day → needs ~350 concurrent workers at steady state, plus proxy pool, rate limits, and shard-aware scheduling.
- Therefore: **job-per-profile**, **idempotent scrapes**, **indexed snapshots by (profile_id, date)**, **proxy-aware scraper**, **queue priority for retries**.

---

## Bounded contexts (clean architecture)

```
┌─────────────┐     ┌─────────────┐     ┌──────────────────────────┐
│  apps/web   │────▶│  apps/api   │────▶│  MongoDB                 │
│  Next.js    │     │  FastAPI    │     │  Redis (broker + cache)  │
└─────────────┘     └──────┬──────┘     └──────────────────────────┘
                           │ enqueue
                           ▼
                    ┌──────────────┐
                    │ apps/worker  │
                    │ Celery       │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        scraper/      analytics/    notifications/
        Playwright    metrics       thresholds
```

### Layer rules (API & workers)

1. **Routers / tasks** — HTTP or Celery entry only. No SQL. No Playwright.
2. **Services** — business rules (add profile, pause tracking, compute growth).
3. **Repositories** — persistence only.
4. **Domain models** — SQLAlchemy entities + pure domain helpers.
5. **Integrations** — Instagram scraper, email/push, object storage for media thumbnails.

No cross-layer imports upward. Shared code lives in `packages/`.

---

## Monorepo map

```
INSTASCOPE/
├── apps/
│   ├── web/                 # Next.js UI (product surface)
│   ├── api/                 # FastAPI (source of truth for mutations)
│   └── worker/              # Celery app + beat schedule
├── packages/
│   ├── python-shared/       # Beanie documents, schemas, settings (used by api + worker)
│   └── ts-shared/           # Shared TS types / API client (generated from OpenAPI later)
├── scraper/                 # Playwright scraper package (imported by worker)
├── infra/
│   ├── docker/              # Dockerfiles + compose
│   ├── postgres/            # init, partitioning helpers
│   └── redis/               # redis config notes
├── docs/
│   ├── architecture/        # this phase + later ADRs
│   ├── api/                 # OpenAPI notes
│   ├── database/            # ERD + migration policy
│   └── ui/                  # wireframes, design tokens
└── scripts/                 # seed, generate-client, migrate helpers
```

### Why `scraper/` is not inside `apps/worker/`

The scraper is a **replaceable integration**. Tomorrow it might use a residential proxy provider API or a headless farm. Keeping it as its own package forces a clean interface:

```python
scrape_profile(username: str, *, proxy: ProxyConfig | None) -> ScrapeResult
```

Workers orchestrate; scrapers fetch.

### Why `packages/python-shared/`

API and workers must agree on:

- User / Profile / Snapshot / Job documents
- Settings (env)
- Job payload schemas

One package → one Beanie model registry; indexes declared on documents.

---

## App-level folder contracts

### `apps/web` (Next.js)

```
apps/web/
├── app/                      # App Router routes only
│   ├── (auth)/               # login, signup, forgot-password
│   ├── (dashboard)/          # shell: sidebar + topbar
│   │   ├── overview/
│   │   ├── profiles/
│   │   │   └── [id]/
│   │   ├── notifications/
│   │   ├── imports/
│   │   └── settings/
│   └── api/                  # BFF proxies only if needed (prefer direct FastAPI)
├── components/
│   ├── ui/                   # shadcn primitives
│   ├── charts/
│   ├── profiles/
│   ├── layout/
│   └── empty-states/
├── features/                 # feature modules (hooks + UI colocated)
├── hooks/
├── lib/                      # api client, auth, cn(), formatters
├── styles/
└── stores/                   # client UI state only (theme, selection) — not server data
```

**Rule:** TanStack Query owns server state. Zustand/context owns ephemeral UI (selected rows, sidebar collapsed).

### `apps/api` (FastAPI)

```
apps/api/
├── app/
│   ├── main.py
│   ├── deps.py               # auth, db session
│   ├── routers/              # thin HTTP adapters
│   ├── middleware/
│   └── lifespan.py
└── tests/
```

Business logic lives in `packages/python-shared` services so workers can call the same “complete scrape → write snapshot → recompute metrics → emit notifications” pipeline.

### `apps/worker`

```
apps/worker/
├── celery_app.py
├── beat_schedule.py          # daily fan-out
├── tasks/
│   ├── scrape_profile.py     # one profile per task
│   ├── fanout_daily.py       # enqueue all due profiles
│   ├── retry_failed.py
│   └── recompute_metrics.py
└── concurrency.py            # rate limits, per-proxy caps
```

### `scraper/`

```
scraper/
├── browser.py                # Playwright context factory + proxy
├── profile.py
├── posts.py
├── parsers/
├── retries.py
└── types.py                  # ScrapeResult DTOs
```

---

## Data ownership (preview for Phase 2)

| Entity | Owns | Does not store |
|---|---|---|
| `users` | identity, prefs | profile metrics |
| `profiles` | Instagram identity + tracking state | historical follower counts |
| `profile_snapshots` | daily point-in-time metrics | post lists |
| `posts` | current known posts (upsert by IG id) | engagement history (optional `post_snapshots` later) |
| `jobs` | queue metadata / status | scrape payload blobs long-term |
| `scrape_logs` | attempt diagnostics | business metrics |
| `notifications` | user-facing events | raw scrape HTML |
| `settings` | org/user thresholds | secrets in plaintext (use env/secrets manager) |

**Normalization rule:** Follower count “today” lives in the latest snapshot (or a cached column on `profiles` updated transactionally after scrape). Charts always read snapshots / metrics tables — never invent history from mutable profile columns alone.

---

## Scheduling strategy (preview for Phase 9)

1. **Celery Beat** fires `fanout_daily` once per day (timezone-aware per workspace later).
2. Fan-out queries due profiles in **keyset batches** (never `SELECT *` into memory).
3. Each profile → `scrape_profile.delay(profile_id)` with jitter to smooth load.
4. Failures → retry with exponential backoff; after N failures → `status=failed`, notify.
5. Priority queue for manual “Refresh now” vs nightly batch.

---

## Frontend product architecture (preview for Phases 4–7)

Inspiration (not imitation): Stripe density + Linear motion + Vercel calm + Datadog chart clarity.

Principles encoded into folders:

- `components/ui` = primitives (Button, Input, Table) — never business copy
- `features/*` = product surfaces with empty/loading/error states required
- `components/charts` = shared Recharts/Visx wrappers with consistent axes/tooltips
- Motion lives at route and counter level — not on every pixel

---

## Phase gate

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Folder architecture + rationale | **This document + tree** |
| 2 | Database schema (SQLAlchemy + ERD) | Next |
| 3 | API architecture (routes, auth, jobs) | |
| 4 | UI wireframe / information architecture | |
| 5 | Design system (tokens, typography, components) | |
| 6 | Authentication | |
| 7 | Dashboard | |
| 8 | Scraper | |
| 9 | Workers | |
| 10 | Analytics | |
| 11 | Deployment | |

---

## Non-negotiables for later phases

1. One scrape job = one profile.
2. Snapshots are immutable append-only.
3. Dashboard reads precomputed metrics.
4. Scraper never imported by FastAPI routers.
5. UI never talks to Redis/Postgres directly.
6. Every list view has search, filter, sort, pagination, empty & loading states.
7. Visual quality is a product requirement, not polish-at-the-end.
