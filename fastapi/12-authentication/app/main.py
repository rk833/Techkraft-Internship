"""Module 11 - Database and Migrations."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.database import engine
from app.dependencies import DbSession
from app.handlers import handle_unexpected_error, register_error_handlers
from app.logging_config import setup_logging
from app.middleware import (
    REQUEST_ID_HEADER,
    RESPONSE_TIME_HEADER,
    RequestContextMiddleware,
    add_security_headers_middleware,
)
from app.routers import admin, auth, notes
from app.schemas import ERROR_RESPONSES

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger("api.lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown.

    Note what is deliberately absent: Base.metadata.create_all(). The schema is
    owned by Alembic. Calling create_all here would build tables from the models
    on first run, which then diverge from the migration history invisibly, and
    the first deployment to a database that has been migrated would fail in a
    way nobody can reproduce locally.
    """
    # Fail fast on a missing or weak signing secret. A service that starts
    # without one is a service anyone can mint admin tokens for.
    settings.validate_secret()
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    logger.info("startup: database reachable at %s", _safe_url(settings.resolved_database_url))
    logger.info("startup: jwt %s, access token %sm, refresh token %sd",
                settings.jwt_algorithm,
                settings.access_token_expire_minutes,
                settings.refresh_token_expire_days)
    yield
    engine.dispose()
    logger.info("shutdown: connection pool disposed")


def _safe_url(url: str) -> str:
    """Strip any password before a database URL reaches the logs."""
    if "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    _, _, host = rest.rpartition("@")
    return f"{scheme}://***@{host}"


app = FastAPI(
    title="Secured Notes API",
    description="Module 12 of the FastAPI learning journey - JWT authentication and RBAC.",
    version="0.3.0",
    lifespan=lifespan,
    responses=ERROR_RESPONSES,
)

register_error_handlers(app)

app.add_middleware(GZipMiddleware, minimum_size=settings.gzip_minimum_size)
app.add_middleware(RequestContextMiddleware, on_unhandled=handle_unexpected_error)
add_security_headers_middleware(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
    expose_headers=[REQUEST_ID_HEADER, RESPONSE_TIME_HEADER],
    max_age=600,
)

app.include_router(auth.router)
app.include_router(notes.router)
app.include_router(admin.router)


@app.get("/health", tags=["general"], summary="Service health check")
def health_check(db: DbSession) -> dict:
    """Report that the service is running and the database answers.

    Uses the session dependency rather than the engine directly, so a test that
    overrides get_db redirects this too. An endpoint reaching past its
    dependency is exactly the seam module 09 was about not breaking.
    """
    db.execute(text("SELECT 1"))
    return {"status": "ok", "version": app.version, "database": "reachable"}
