# Folder structure — Phase 1

Canonical tree. Empty folders use `.gitkeep` until Phase 2+.

```
INSTASCOPE/
├── ARCHITECTURE.md
├── README.md
├── .gitignore
│
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── routers/          # HTTP adapters only
│   │   │   └── middleware/
│   │   └── tests/
│   ├── worker/
│   │   ├── tasks/                # Celery tasks (orchestration)
│   │   └── tests/
│   └── web/
│       ├── app/
│       │   ├── (auth)/
│       │   │   ├── login/
│       │   │   ├── signup/
│       │   │   └── forgot-password/
│       │   └── (dashboard)/
│       │       ├── overview/
│       │       ├── profiles/[id]/
│       │       ├── notifications/
│       │       ├── imports/
│       │       ├── analytics/
│       │       └── settings/
│       ├── components/
│       │   ├── ui/               # shadcn primitives
│       │   ├── charts/
│       │   ├── profiles/
│       │   ├── layout/
│       │   ├── empty-states/
│       │   └── skeletons/
│       ├── features/              # product modules
│       │   ├── auth/
│       │   ├── overview/
│       │   ├── profiles/
│       │   ├── analytics/
│       │   ├── notifications/
│       │   └── bulk/
│       ├── hooks/
│       ├── lib/
│       ├── styles/
│       ├── stores/               # UI state only
│       └── public/
│
├── packages/
│   ├── python-shared/
│   │   ├── alembic/versions/
│   │   └── instascope_shared/
│   │       ├── core/             # settings, security helpers
│   │       ├── db/               # engine, session
│   │       ├── domain/           # pure domain rules
│   │       ├── models/           # SQLAlchemy entities
│   │       ├── schemas/          # Pydantic DTOs
│   │       ├── repositories/
│   │       ├── services/
│   │       ├── analytics/
│   │       └── notifications/
│   └── ts-shared/
│       └── src/
│           ├── types/
│           └── api/              # generated OpenAPI client (later)
│
├── scraper/
│   ├── instascope_scraper/
│   │   └── parsers/
│   └── tests/
│
├── infra/
│   ├── docker/
│   ├── postgres/
│   └── redis/
│
├── docs/
│   ├── architecture/
│   ├── api/
│   ├── database/
│   └── ui/
│
└── scripts/
```

## Import boundaries

| From | May import | Must not import |
|------|------------|-----------------|
| `apps/web` | `packages/ts-shared`, own features | Python, Redis, Playwright |
| `apps/api` | `packages/python-shared` | `scraper`, Celery task bodies |
| `apps/worker` | `packages/python-shared`, `scraper` | Next.js, FastAPI routers |
| `scraper` | stdlib + Playwright + own types | DB models, FastAPI |
| `python-shared` | SQLAlchemy, Pydantic | Playwright, FastAPI `Request` |

Enforced later with lint/import-linter rules in Phase 11.
