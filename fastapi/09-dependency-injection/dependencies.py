"""The dependency toolkit.

Every reusable piece the routers need lives here: pagination, a request-scoped
logger, store access, a 404-resolving path dependency, a yield-based unit of
work, and two guards.

The point of collecting them in one module is that a router then reads as a
list of what an endpoint needs rather than as a list of what it has to set up.
"""

import logging
from typing import Annotated, Any, Iterator

from fastapi import Depends, Header, Query, Request

from config import Settings, get_settings
from context import get_request_id
from errors import AppError, ErrorCode, NotFoundError
from store import TaskStore, store as default_store

logger = logging.getLogger("api.deps")

# Yield dependencies append their setup and teardown events here so tests can
# assert that teardown actually ran, and in what order. A real application
# would not keep this; it exists to make an invisible mechanism observable.
EVENTS: list[str] = []


# --- settings ------------------------------------------------------------

SettingsDep = Annotated[Settings, Depends(get_settings)]


# --- pagination ----------------------------------------------------------


class PaginationParams:
    """Pagination, as a class dependency.

    FastAPI treats any callable as a dependency, and a class is callable - so
    Depends(PaginationParams) inspects __init__ and turns its parameters into
    query parameters, exactly as it would for a function.

    A class is the better choice here because pagination is not just two
    values, it is two values plus the behaviour that goes with them. slice()
    and page_of() live with the data instead of being repeated in every
    endpoint that paginates.
    """

    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 20,
        offset: Annotated[int, Query(ge=0, description="Rows to skip")] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset

    def slice(self, items: list) -> list:
        """Return one page of a list."""
        return items[self.offset : self.offset + self.limit]

    def page_of(self, items: list) -> dict:
        """Build the standard page envelope, including the pre-slice total."""
        page = self.slice(items)
        return {
            "total": len(items),
            "count": len(page),
            "limit": self.limit,
            "offset": self.offset,
            "items": page,
        }

    def __repr__(self) -> str:
        return f"PaginationParams(limit={self.limit}, offset={self.offset})"


Pagination = Annotated[PaginationParams, Depends(PaginationParams)]


# --- request scoped logger -----------------------------------------------


def get_request_logger(request: Request) -> logging.LoggerAdapter:
    """A logger already bound to this request.

    Declaring `request: Request` in a dependency is enough for FastAPI to pass
    it; nothing has to be registered. The adapter carries the method and path,
    so an endpoint using it does not repeat them in every message.
    """
    return logging.LoggerAdapter(
        logging.getLogger("api.request.scoped"),
        {"method": request.method, "path": request.url.path, "request_id": get_request_id()},
    )


RequestLogger = Annotated[logging.LoggerAdapter, Depends(get_request_logger)]


# --- store access --------------------------------------------------------


def get_store() -> TaskStore:
    """Provide the task store.

    A one-line indirection with a real purpose: it is the seam. Endpoints
    depend on this function rather than importing the module-level `store`, so
    a test can substitute a different store with dependency_overrides and no
    production code changes. An endpoint that imports the store directly cannot
    be given a different one.
    """
    return default_store


StoreDep = Annotated[TaskStore, Depends(get_store)]


# --- a dependency that resolves a path parameter --------------------------


def get_task_or_404(task_id: int, store: StoreDep) -> dict:
    """Resolve {task_id} to a task, or raise the 404.

    This is a sub-dependency: it depends on get_store, and FastAPI resolves
    that first. It also reads the path parameter directly - a dependency
    receives the same request data an endpoint does.

    In module 08 five handlers each began with the same _require(task_id) call.
    Here the 404 happens before any handler body runs, so those handlers now
    receive a task that is guaranteed to exist and contain no lookup code.
    """
    task = store.get(task_id)
    if task is None:
        raise NotFoundError(f"No task with id {task_id}")
    return task


TaskDep = Annotated[dict, Depends(get_task_or_404)]


# --- yield dependencies ---------------------------------------------------


class UnitOfWork:
    """A stand-in for a database transaction.

    Records what happened to it so a test can assert the sequence. Module 11
    replaces this with a real SQLAlchemy session; the shape of the dependency
    around it does not change.
    """

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self) -> None:
        self.committed = True
        EVENTS.append("uow.commit")

    def rollback(self) -> None:
        self.rolled_back = True
        EVENTS.append("uow.rollback")

    def close(self) -> None:
        self.closed = True
        EVENTS.append("uow.close")


def get_unit_of_work() -> Iterator[UnitOfWork]:
    """Open a unit of work, commit on success, roll back on failure.

    Everything before the yield is setup; everything after is teardown, and it
    runs after the response has been generated. Wrapping the yield in try/except
    is what lets the dependency see whether the endpoint succeeded.

    This is the pattern module 11 uses for the database session. Getting the
    rollback path right here, where the failure can be triggered on demand, is
    much easier than getting it right against a real database.
    """
    uow = UnitOfWork()
    EVENTS.append("uow.begin")
    try:
        yield uow
    except Exception:
        uow.rollback()
        # Re-raising matters. Swallowing it here would turn a failed request
        # into a 200 with an empty body, and the endpoint would appear to have
        # worked.
        raise
    else:
        uow.commit()
    finally:
        uow.close()


UnitOfWorkDep = Annotated[UnitOfWork, Depends(get_unit_of_work)]


def outer_resource() -> Iterator[str]:
    """The outer half of a nested pair, to show teardown ordering."""
    EVENTS.append("outer.setup")
    try:
        yield "outer"
    finally:
        EVENTS.append("outer.teardown")


def inner_resource(outer: Annotated[str, Depends(outer_resource)]) -> Iterator[str]:
    """Depends on outer_resource, so it is set up second and torn down first."""
    EVENTS.append("inner.setup")
    try:
        yield f"inner-of-{outer}"
    finally:
        EVENTS.append("inner.teardown")


# --- guards ---------------------------------------------------------------


class UnauthorisedError(AppError):
    """A missing or wrong API key."""

    status_code = 401
    code = ErrorCode.INVALID_REQUEST
    message = "A valid X-API-Key header is required"


def verify_api_key(
    settings: SettingsDep,
    x_api_key: Annotated[str | None, Header(description="Admin API key")] = None,
) -> None:
    """Reject the request unless the admin key is correct.

    Returns nothing. A dependency used purely for its side effect is attached
    with `dependencies=[Depends(...)]` on the router rather than as a
    parameter, so no endpoint carries an unused argument.

    Header(...) maps x_api_key to the X-API-Key header - FastAPI converts
    underscores to hyphens automatically.
    """
    if not settings.admin_api_key:
        raise UnauthorisedError("Admin access is not configured on this server")
    if x_api_key != settings.admin_api_key:
        raise UnauthorisedError()


def record_request(request: Request) -> None:
    """An application-level dependency, run for every route.

    Registered on FastAPI(dependencies=[...]). Useful for a cross-cutting
    concern that needs the dependency system - it can raise HTTP errors and
    depend on other dependencies, which middleware cannot do as cleanly.
    """
    request.state.audited = True


# --- caching demonstration -------------------------------------------------


def shared_subdependency(request: Request) -> str:
    """Counts how many times it is called within a single request.

    FastAPI caches a dependency's result per request by default, so a
    dependency needed by three different things is executed once. That is what
    makes a get_current_user dependency cheap to depend on everywhere.
    """
    request.state.shared_calls = getattr(request.state, "shared_calls", 0) + 1
    return "shared-value"


def branch_a(value: Annotated[str, Depends(shared_subdependency)]) -> str:
    """One consumer of the shared dependency."""
    return f"a:{value}"


def branch_b(value: Annotated[str, Depends(shared_subdependency)]) -> str:
    """A second consumer. Still resolves to the same cached call."""
    return f"b:{value}"


def branch_uncached(
    # use_cache=False opts out, forcing a fresh call. Correct when the
    # dependency is not idempotent, wrong for anything expensive.
    value: Annotated[str, Depends(shared_subdependency, use_cache=False)],
) -> str:
    """A third consumer that deliberately bypasses the cache."""
    return f"c:{value}"


def describe_dependency(value: Any) -> dict:
    """Small helper so the diagnostics endpoints stay readable."""
    return {"resolved": value}
