"""Module 03 - Path and Query Parameters."""

from fastapi import FastAPI

from routers import products

app = FastAPI(
    title="Product Search API",
    description="Module 03 of the FastAPI learning journey - path and query parameters.",
    version="0.1.0",
)

app.include_router(products.router)


@app.get("/health", tags=["general"], summary="Service health check")
def health_check() -> dict[str, str]:
    """Report that the service is running."""
    return {"status": "ok", "version": app.version}
