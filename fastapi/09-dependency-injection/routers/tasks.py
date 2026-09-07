"""Task routes, refactored onto the dependency toolkit.

Compare with module 08. Every handler that took an id used to start with a
_require(task_id) lookup; now the task arrives already resolved. Every handler
that paginated used to declare limit and offset and slice by hand; now it takes
one Pagination parameter.
"""

from typing import Annotated

from fastapi import APIRouter, Query, status

from dependencies import (
    Pagination,
    RequestLogger,
    StoreDep,
    TaskDep,
    UnitOfWorkDep,
)
from errors import ConflictError
from schemas import (
    ERROR_RESPONSES,
    Priority,
    TaskCreate,
    TaskPage,
    TaskRead,
    TaskReplace,
    TaskStatus,
    TaskUpdate,
)

router = APIRouter(prefix="/tasks", tags=["tasks"], responses=ERROR_RESPONSES)


@router.get("", response_model=TaskPage, summary="List tasks")
def list_tasks(
    store: StoreDep,
    page: Pagination,
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority: Annotated[Priority | None, Query()] = None,
    q: Annotated[str | None, Query(min_length=2, max_length=60)] = None,
) -> dict:
    """Return a filtered, paginated page of tasks.

    The limit and offset query parameters still exist and are still validated -
    they are declared on PaginationParams.__init__ rather than here.
    """
    results = store.list()
    if status_filter is not None:
        results = [t for t in results if t["status"] == status_filter]
    if priority is not None:
        results = [t for t in results if t["priority"] == priority]
    if q is not None:
        needle = q.casefold()
        results = [t for t in results if needle in t["title"].casefold()]
    return page.page_of(results)


@router.get("/search", response_model=TaskPage, summary="Search task titles")
def search_tasks(
    store: StoreDep,
    page: Pagination,
    q: Annotated[str, Query(min_length=2, max_length=60)],
) -> dict:
    """Second consumer of the pagination dependency."""
    needle = q.casefold()
    return page.page_of([t for t in store.list() if needle in t["title"].casefold()])


@router.get("/tagged/{tag}", response_model=TaskPage, summary="Tasks with a tag")
def tasks_by_tag(store: StoreDep, page: Pagination, tag: str) -> dict:
    """Third consumer of the pagination dependency."""
    return page.page_of([t for t in store.list() if tag in t["tags"]])


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED, summary="Create a task")
def create_task(
    payload: TaskCreate,
    store: StoreDep,
    uow: UnitOfWorkDep,
    log: RequestLogger,
) -> dict:
    """Create a task inside a unit of work.

    The commit is not written here. If this function returns, the dependency
    commits; if it raises, the dependency rolls back. Neither path is the
    handler's responsibility.
    """
    if store.find_by_title(payload.title):
        raise ConflictError(
            f"A task titled {payload.title!r} already exists",
            details=[{"field": "body.title", "message": "must be unique", "type": "duplicate"}],
        )
    task = store.create(payload.model_dump())
    log.info("created task %s", task["id"])
    return task


@router.get("/{task_id}", response_model=TaskRead, summary="Get one task")
def get_task(task: TaskDep) -> dict:
    """Return a single task.

    No task_id parameter and no lookup. get_task_or_404 consumed the path
    parameter, resolved it, and raised the 404 before this ran.
    """
    return task


@router.put("/{task_id}", response_model=TaskRead, summary="Replace a task")
def replace_task(task: TaskDep, payload: TaskReplace, store: StoreDep, uow: UnitOfWorkDep) -> dict:
    """Replace a task entirely."""
    return store.replace(task["id"], payload.model_dump())


@router.patch("/{task_id}", response_model=TaskRead, summary="Update a task")
def update_task(task: TaskDep, payload: TaskUpdate, store: StoreDep, uow: UnitOfWorkDep) -> dict:
    """Update only the fields the client sent."""
    return store.update(task["id"], payload.model_dump(exclude_unset=True))


@router.post("/{task_id}/complete", response_model=TaskRead, summary="Mark a task done")
def complete_task(task: TaskDep, store: StoreDep, uow: UnitOfWorkDep) -> dict:
    """Move a task to done."""
    if task["status"] == TaskStatus.DONE:
        raise ConflictError(f"Task {task['id']} is already done")
    return store.update(task["id"], {"status": TaskStatus.DONE})


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a task")
def delete_task(task: TaskDep, store: StoreDep, uow: UnitOfWorkDep) -> None:
    """Delete a task."""
    store.delete(task["id"])
