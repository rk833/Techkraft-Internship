"""Module 08 - CRUD Operations and Testing."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from config import get_settings
from handlers import handle_unexpected_error, register_error_handlers
from logging_config import setup_logging
from middleware import (
    REQUEST_ID_HEADER,
    RESPONSE_TIME_HEADER,
    RequestContextMiddleware,
    add_security_headers_middleware,
)
from routers import tasks
from schemas import ERROR_RESPONSES

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger("api.lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown."""
    logger.info("startup: task manager in %s mode", settings.environment)
    yield
    logger.info("shutdown: releasing resources")


app = FastAPI(
    title="Task Manager API",
    description="Module 08 of the FastAPI learning journey - CRUD and pytest.",
    version="0.1.0",
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
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
    expose_headers=[REQUEST_ID_HEADER, RESPONSE_TIME_HEADER],
    max_age=600,
)

app.include_router(tasks.router)


@app.get("/health", tags=["general"], summary="Service health check")
def health_check() -> dict[str, str]:
    """Report that the service is running."""
    return {"status": "ok", "version": app.version, "environment": settings.environment}
