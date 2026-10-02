"""FastAPI application factory."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.config import Settings
from app.errors import AppError
from app.models.schemas import ErrorResponse, HealthResponse
from app.services.cache import TTLCache
from app.services.catalog import BookCatalogService
from app.services.parser import WebsiteParser
from app.services.rate_limiter import SlidingWindowRateLimiter
from app.services.scraper import WebsiteClient
from app.utils.logging import configure_logging, get_logger

log = get_logger("main")

DESCRIPTION = """
A REST API in front of **books.toscrape.com**, a public sandbox site that has **no API**.
This service reads the site's *public HTML pages*, normalizes them, and exposes clean JSON.

The API is an abstraction created by this project - it is not provided by the website, and
it depends on the website's current HTML structure (see `docs/limitations.md`).
"""


def _error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    body = ErrorResponse(error=code, message=message, status_code=status)
    return JSONResponse(status_code=status, content=body.model_dump(), headers=headers)


def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Build the app. ``transport`` lets tests swap the network for fixtures."""
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)

    cache: TTLCache[str] = TTLCache(settings.cache_ttl_seconds, settings.cache_max_entries)
    client = WebsiteClient(settings, cache, transport=transport)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await client.aclose()

    app = FastAPI(
        title="Books Catalog API (reverse-engineered)",
        version="1.0.0",
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.cache = cache
    app.state.client = client
    app.state.limiter = SlidingWindowRateLimiter(
        settings.rate_limit_requests, settings.rate_limit_window_seconds
    )
    app.state.catalog = BookCatalogService(client, WebsiteParser(), settings)

    @app.middleware("http")
    async def request_logging(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = uuid.uuid4().hex[:12]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error", extra={"request_id": request_id, "path": request.url.path})
            raise
        response.headers["X-Request-ID"] = request_id
        log.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,  # query string intentionally not logged
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return response

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.status_code, exc.error, exc.message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        parts = []
        for e in exc.errors()[:3]:
            loc = ".".join(str(p) for p in e["loc"] if p not in ("query", "path"))
            parts.append(f"{loc}: {e['msg']}")
        return _error(400, "bad_request", "Invalid request. " + "; ".join(parts))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        return _error(exc.status_code, codes.get(exc.status_code, "http_error"), str(exc.detail))

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Details are logged by the middleware; the client only gets a generic message.
        return _error(500, "internal_error", "An unexpected error occurred.")

    @app.get("/health", response_model=HealthResponse, tags=["meta"], summary="Liveness check")
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    app.include_router(router)
    return app


app = create_app()
