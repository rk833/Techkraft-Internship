"""Diagnostics routes.

These exist to make the dependency system observable. They are not the kind of
endpoint a real API would ship, and they are the only honest way to demonstrate
behaviour that otherwise leaves no trace in a response.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from dependencies import (
    EVENTS,
    Pagination,
    RequestLogger,
    SettingsDep,
    UnitOfWorkDep,
    branch_a,
    branch_b,
    branch_uncached,
    inner_resource,
)
from schemas import ERROR_RESPONSES

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"], responses=ERROR_RESPONSES)


@router.get("/pagination", summary="Show the resolved pagination dependency")
def show_pagination(page: Pagination) -> dict:
    """Return what PaginationParams resolved to.

    The limit and offset query parameters are validated exactly as if they were
    declared on this function, because as far as FastAPI is concerned they were.
    """
    return {"limit": page.limit, "offset": page.offset, "repr": repr(page)}


@router.get("/cache", summary="Show per-request dependency caching")
def show_cache(
    request: Request,
    a: Annotated[str, Depends(branch_a)],
    b: Annotated[str, Depends(branch_b)],
) -> dict:
    """Two branches, one shared sub-dependency.

    shared_subdependency is reached twice in the graph but executed once,
    because FastAPI caches a dependency result for the duration of a request.
    """
    return {"a": a, "b": b, "shared_calls": request.state.shared_calls}


@router.get("/cache-off", summary="Show use_cache=False")
def show_cache_disabled(
    request: Request,
    a: Annotated[str, Depends(branch_a)],
    b: Annotated[str, Depends(branch_b)],
    c: Annotated[str, Depends(branch_uncached)],
) -> dict:
    """Adding one uncached consumer raises the call count by exactly one."""
    return {"a": a, "b": b, "c": c, "shared_calls": request.state.shared_calls}


@router.get("/nested", summary="Show yield teardown ordering")
def show_nested(resource: Annotated[str, Depends(inner_resource)]) -> dict:
    """Set up two nested yield dependencies.

    The response reports the setup order. The teardown order only appears in
    EVENTS after the response has been produced, which is exactly why the tests
    assert against EVENTS rather than against this body.
    """
    return {"resource": resource, "events_so_far": list(EVENTS)}


@router.get("/unit-of-work", summary="A request that commits")
def uow_success(uow: UnitOfWorkDep) -> dict:
    """Return normally, so the dependency commits."""
    return {"committed_at_this_point": uow.committed}


@router.get("/unit-of-work/fail", summary="A request that rolls back")
def uow_failure(uow: UnitOfWorkDep) -> dict:
    """Raise, so the dependency rolls back instead of committing."""
    raise RuntimeError("endpoint failed after the unit of work was opened")


@router.get("/unit-of-work/http-error", summary="A handled error inside a unit of work")
def uow_http_error(uow: UnitOfWorkDep) -> dict:
    """Raise an application error rather than an unexpected one.

    Worth its own endpoint because whether a deliberately raised HTTP error
    counts as a failure for the transaction is not obvious, and the answer
    decides whether a 404 leaves a half-finished write committed.
    """
    from errors import NotFoundError

    raise NotFoundError("deliberate 404 raised inside a unit of work")


@router.get("/context", summary="Settings and request-scoped logger")
def show_context(settings: SettingsDep, log: RequestLogger, request: Request) -> dict:
    """Show that settings and the logger arrived by injection."""
    log.info("diagnostics context requested")
    return {
        "app_name": settings.app_name,
        "environment": settings.environment,
        "audited_by_app_dependency": getattr(request.state, "audited", False),
    }
