from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import analytics, auth, notifications, profiles, settings, spark
from instascope_shared.core.config import get_settings
from instascope_shared.db.mongodb import close_db, connect_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await connect_db()
    yield
    await close_db()


def create_app() -> FastAPI:
    cfg = get_settings()
    app = FastAPI(title=cfg.app_name, version="0.1.0", lifespan=lifespan)

    origins = list(cfg.cors_origin_list)
    # Dev convenience: allow any localhost / 127.0.0.1 port (UI may bind 3000 or 3001)
    if cfg.environment == "development" or cfg.debug:
        origins = list(
            dict.fromkeys(
                [
                    *origins,
                    "http://localhost:3000",
                    "http://localhost:3001",
                    "http://127.0.0.1:3000",
                    "http://127.0.0.1:3001",
                ]
            )
        )

    # Always allow this host's web UI (common prod miss: CORS_ORIGINS only has localhost)
    for extra in (
        "http://62.238.57.52:3000",
        "http://62.238.57.52:3001",
        getattr(cfg, "web_origin", None) or "",
    ):
        if extra and extra.strip():
            origins.append(extra.strip())
    origins = list(dict.fromkeys(origins))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|62\.238\.57\.52)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    prefix = cfg.api_prefix
    app.include_router(auth.router, prefix=prefix)
    app.include_router(profiles.router, prefix=prefix)
    app.include_router(analytics.router, prefix=prefix)
    app.include_router(notifications.router, prefix=prefix)
    app.include_router(settings.router, prefix=prefix)
    app.include_router(spark.router, prefix=prefix)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": cfg.app_name}

    return app


app = create_app()
