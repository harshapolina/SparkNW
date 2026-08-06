from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import analytics, auth, notifications, profiles, settings, spark
from instascope_shared.core.config import get_settings
from instascope_shared.db.mongodb import close_db, connect_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    logging.getLogger("instascope").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    await connect_db()
    # Orphaned scrape_progress.active survives API restarts and blocks the UI.
    try:
        from app.scrape_queue import clear_stale_scrape_progress

        cleared = await clear_stale_scrape_progress()
        if cleared:
            logging.getLogger("instascope.api").warning(
                "startup cleared %s stale scrape progress marker(s)", cleared
            )
    except Exception:
        logging.getLogger("instascope.api").exception("startup scrape cleanup failed")
    yield
    await close_db()


def _cors_headers(request: Request, origins: list[str]) -> dict[str, str]:
    origin = request.headers.get("origin") or ""
    allow = origin if origin in origins else (origins[0] if origins else "*")
    # Always echo request origin when it matches our host regex (prod IP / localhost)
    if origin and (
        origin in origins
        or "62.238.57.52" in origin
        or "localhost" in origin
        or "127.0.0.1" in origin
    ):
        allow = origin
    return {
        "Access-Control-Allow-Origin": allow,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    }


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
        allow_origins=origins or ["*"],
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|62\.238\.57\.52)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """Ensure CORS headers exist even on errors (browser otherwise shows 'Failed to fetch')."""
        from fastapi import HTTPException
        from fastapi.exceptions import RequestValidationError

        headers = _cors_headers(request, origins)
        if isinstance(exc, HTTPException):
            detail = exc.detail
            return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=headers)
        if isinstance(exc, RequestValidationError):
            return JSONResponse(
                status_code=422,
                content={"detail": exc.errors()},
                headers=headers,
            )
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc)[:400] or "Internal server error"},
            headers=headers,
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

    @app.options("/{full_path:path}")
    async def preflight(full_path: str, request: Request):
        return JSONResponse(content={"ok": True}, headers=_cors_headers(request, origins))

    return app


app = create_app()
