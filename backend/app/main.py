"""
Attora — FastAPI Application

Main application entry point. Configures middleware, CORS, routes,
error handling, and lifecycle events.
"""

import logging
import uuid
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.jobs.scheduler import build_follow_up_scheduler
from app.olap import get_object_storage_adapter, get_query_adapter
from app.redis import close_redis, init_redis
from app.api import api_router
from app.middleware.rate_limit import RateLimitMiddleware

# ── Logging ──────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("attora")

# Follow-up APScheduler when ``follow_up_scheduler_enabled`` (OLAP/Hyros stay in jobs container).
scheduler = None


# ── Lifecycle ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle."""
    global scheduler

    # Startup
    logger.info(f"Starting {settings.app_name} ({settings.app_env})")
    storage_adapter = get_object_storage_adapter()
    query_adapter = get_query_adapter()
    logger.info(
        "OLAP providers: storage=%s query=%s root=%s",
        storage_adapter.provider,
        query_adapter.provider,
        settings.olap_s3_uri,
    )

    # Initialize Redis
    try:
        await init_redis()
        logger.info("Redis connection pool initialized")
    except Exception as e:
        logger.warning(f"Redis connection failed (non-fatal): {e}")

    if settings.follow_up_scheduler_enabled:
        scheduler = build_follow_up_scheduler()
        scheduler.start()
        logger.info("Follow-up scheduler started")

    yield

    # Shutdown
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Follow-up scheduler stopped")

    logger.info("Shutting down...")
    await close_redis()
    logger.info("Redis connection pool closed")


# ── App ──────────────────────────────────────────────────────

_docs_enabled = settings.debug or settings.expose_api_docs
app = FastAPI(
    title=settings.app_name,
    description="White-Labeled ManyChat Platform with AI Conversation Engine",
    version="1.0.0",
    docs_url="/api/docs" if _docs_enabled else None,
    redoc_url="/api/redoc" if _docs_enabled else None,
    openapi_url="/api/openapi.json" if _docs_enabled else None,
    lifespan=lifespan,
)


# ── Middleware (order matters — last added = first executed) ──

# Rate limiting
app.add_middleware(RateLimitMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
)


# ── Request ID Middleware ────────────────────────────────────

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add a unique X-Request-ID header to every request/response."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Error Handlers ───────────────────────────────────────────

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle HTTP exceptions with consistent JSON format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "status_code": exc.status_code,
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle validation errors with consistent JSON format."""
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "status_code": 422,
            "errors": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions — never leak stack traces."""
    logger.exception(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "status_code": 500,
        },
    )


# ── Routes ───────────────────────────────────────────────────

app.include_router(api_router, prefix="/api")
