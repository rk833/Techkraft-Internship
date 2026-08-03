"""Module 02 - Routing and APIRouter.

main.py owns the application and nothing else. It creates the app, registers
the routers, and stays short. Every actual endpoint lives in routers/.
"""

from fastapi import FastAPI

from routers import authors, books

app = FastAPI(
    title="Book Catalogue API",
    description="Module 02 of the FastAPI learning journey - routing and APIRouter.",
    version="0.1.0",
)

# Each router already carries its own prefix and tags, so registration is one
# line per resource. Adding a resource means adding a file and a line here.
app.include_router(books.router)
app.include_router(authors.router)


@app.get("/health", tags=["general"], summary="Service health check")
def health_check() -> dict[str, str]:
    """Report that the service is running."""
    return {"status": "ok", "version": app.version}
