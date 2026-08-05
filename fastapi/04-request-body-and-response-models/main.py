"""Module 04 - Request Body and Response Models."""

from fastapi import FastAPI

from routers import users

app = FastAPI(
    title="User Registration API",
    description="Module 04 of the FastAPI learning journey - request bodies and response models.",
    version="0.1.0",
)

app.include_router(users.router)


@app.get("/health", tags=["general"], summary="Service health check")
def health_check() -> dict[str, str]:
    """Report that the service is running."""
    return {"status": "ok", "version": app.version}
