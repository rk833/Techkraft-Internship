"""Module 06 - Error Handling."""

from fastapi import FastAPI, HTTPException

from config import get_settings
from handlers import register_error_handlers
from logging_config import setup_logging
from routers import products
from schemas import ERROR_RESPONSES

settings = get_settings()
setup_logging(settings.log_level)

app = FastAPI(
    title="Resilient Item API",
    description="Module 06 of the FastAPI learning journey - a uniform error contract.",
    version="0.1.0",
    responses=ERROR_RESPONSES,
)

# Registered before any route runs, so nothing can slip past them.
register_error_handlers(app)

app.include_router(products.router)


@app.get("/teapot", tags=["general"], summary="Raise a plain HTTPException")
def teapot() -> dict:
    """Raise a bare HTTPException rather than one of our own error types.

    Third-party code and FastAPI's own security dependencies raise
    HTTPException, so the envelope has to survive it. Nothing here was written
    with our error types in mind, and the response is still the same shape.
    """
    raise HTTPException(status_code=418, detail="I refuse to brew coffee")


@app.get("/health", tags=["general"], summary="Service health check")
def health_check() -> dict[str, str]:
    """Report that the service is running."""
    return {"status": "ok", "version": app.version, "environment": settings.environment}
