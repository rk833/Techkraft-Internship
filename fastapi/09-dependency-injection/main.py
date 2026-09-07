"""Module 09 - Dependency Injection."""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from config import get_settings
from dependencies import record_request
from handlers import handle_unexpected_error, register_error_handlers
from logging_config import setup_logging
from middleware import (
    REQUEST_ID_HEADER,
    RESPONSE_TIME_HEADER,
    RequestContextMiddleware,
    add_security_headers_middleware,
)
from routers import admin, diagnostics, tasks
from schemas import ERROR_RESPONSES

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger("api.lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown."""
    logger.info("startup: dependency toolkit in %s mode", settings.environment)
    logger.info("startup: admin key configured: %s", bool(settings.admin_api_key))
    yield
    logger.info("shutdown: releasing resources")


app = FastAPI(
    title="Dependency Toolkit API",
    description="Module 09 of the FastAPI learning journey - Depends() end to end.",
    version="0.1.0",
    lifespan=lifespan,
    responses=ERROR_RESPONSES,
    # An application-level dependency runs for every route on the app, before
    # any router or endpoint dependency. Use it only for something genuinely
    # universal: it applies to /docs and /openapi.json too.
    dependencies=[Depends(record_request)],
)

register_error_handlers(app)

app.add_middleware(GZipMiddleware, minimum_size=settings.gzip_minimum_size)
app.add_middleware(RequestContextMiddleware, on_unhandled=handle_unexpected_error)
add_security_headers_middleware(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", REQUEST_ID_HEADER],
    expose_headers=[REQUEST_ID_HEADER, RESPONSE_TIME_HEADER],
    max_age=600,
)

app.include_router(tasks.router)
app.include_router(admin.router)
app.include_router(diagnostics.router)


@app.get("/health", tags=["general"], summary="Service health check")
def health_check() -> dict[str, str]:
    """Report that the service is running."""
    return {"status": "ok", "version": app.version, "environment": settings.environment}
