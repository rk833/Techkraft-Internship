"""Module 01 - Hello FastAPI.

The smallest useful FastAPI application: two endpoints and the automatic
documentation that FastAPI generates from them.
"""

from fastapi import FastAPI

# The metadata passed here is not decoration. FastAPI puts all of it into the
# generated OpenAPI schema, which is what renders the /docs and /redoc pages.
app = FastAPI(
    title="Hello FastAPI",
    description="Module 01 of the FastAPI learning journey.",
    version="0.1.0",
)


@app.get("/", tags=["general"], summary="Welcome message")
def read_root() -> dict[str, str]:
    """Return a welcome message.

    The dict returned here is serialised to JSON automatically. The return type
    annotation is what FastAPI uses to document the response shape.
    """
    return {"message": "Welcome to the FastAPI learning journey"}


@app.get("/health", tags=["general"], summary="Service health check")
def health_check() -> dict[str, str]:
    """Report that the service is running.

    A health endpoint exists so that something outside the application - a load
    balancer, Docker, a monitoring tool - can ask whether the process is alive
    without needing to understand any real endpoint.
    """
    return {"status": "ok", "version": app.version}
