"""Module 05 - Pydantic Models and Settings."""

from fastapi import FastAPI

from config import ENV_FILE, get_settings
from routers import orders
from schemas import SettingsRead

settings = get_settings()

app = FastAPI(
    # The title now comes from configuration rather than from a literal, which
    # is the smallest possible demonstration that settings are actually wired in.
    title=f"Order API ({settings.app_name})",
    description="Module 05 of the FastAPI learning journey - Pydantic models and settings.",
    version="0.1.0",
    # Interactive docs are useful in development and are usually turned off in
    # production. Driving that from settings rather than from a hardcoded flag.
    docs_url="/docs" if not settings.is_production else None,
)

app.include_router(orders.router)


@app.get("/config", response_model=SettingsRead, tags=["general"], summary="Show effective settings")
def read_config() -> dict:
    """Return the configuration this process is running with.

    Only non-sensitive values. No endpoint in any module should ever return a
    secret, and the shared .env holds several.
    """
    s = get_settings()
    return {
        **s.model_dump(),
        "is_production": s.is_production,
        "env_file": str(ENV_FILE),
    }


@app.get("/health", tags=["general"], summary="Service health check")
def health_check() -> dict[str, str]:
    """Report that the service is running."""
    return {"status": "ok", "version": app.version, "environment": settings.environment}
