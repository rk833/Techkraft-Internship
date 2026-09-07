"""Module 10 - Async and Concurrency."""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from clients import close_client, open_client
from config import get_settings
from handlers import handle_unexpected_error, register_error_handlers
from logging_config import setup_logging
from middleware import (
    REQUEST_ID_HEADER,
    RESPONSE_TIME_HEADER,
    RequestContextMiddleware,
    add_security_headers_middleware,
)
from routers import aggregate, blocking

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger("api.lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the shared HTTP client at startup, close it at shutdown.

    This is the use case module 07 described in the abstract. One client, one
    connection pool, created once and reused by every request - rather than a
    new client and a new pool per call.
    """
    await open_client(settings)
    logger.info("startup: aggregator ready")
    yield
    await close_client()
    logger.info("shutdown: client closed")


app = FastAPI(
    title="Concurrent Aggregator API",
    description="Module 10 of the FastAPI learning journey - async, the event loop, and concurrency.",
    version="0.1.0",
    lifespan=lifespan,
)

register_error_handlers(app)

app.add_middleware(GZipMiddleware, minimum_size=settings.gzip_minimum_size)
app.add_middleware(RequestContextMiddleware, on_unhandled=handle_unexpected_error)
add_security_headers_middleware(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
    expose_headers=[REQUEST_ID_HEADER, RESPONSE_TIME_HEADER],
    max_age=600,
)

app.include_router(aggregate.router)
app.include_router(blocking.router)


@app.get("/health", tags=["general"], summary="Service health check")
async def health_check() -> dict:
    """A deliberately trivial async endpoint.

    Its value in this module is as a probe: hit it while a blocking endpoint is
    running and its latency reveals whether the event loop is free. A healthy
    server answers in under a millisecond.
    """
    return {
        "status": "ok",
        "version": app.version,
        "at": round(time.perf_counter(), 3),
    }
