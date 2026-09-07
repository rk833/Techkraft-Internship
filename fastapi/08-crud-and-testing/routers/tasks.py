"""Task routes.

Five CRUD operations plus one state transition. Every handler talks to the
store and raises domain errors; none of them builds a response or knows what
an error looks like on the wire.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from errors import ConflictError, NotFoundError
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
from store import store

logger = logging.getLogger("api.tasks")

router = APIRouter(prefix="/tasks", tags=["tasks"], responses=ERROR_RESPONSES)

TaskId = Annotated[int, Path(ge=1, description="Task id")]


def _require(task_id: int) -> dict:
    """Return a task or raise the 404.

    Four handlers need exactly this. Extracting it means the message is worded
    once, so a client sees the same text whichever endpoint it hit.
    """
    task = store.get(task_id)
    if task is None:
        raise NotFoundError(f"No task with id {task_id}")
    return task


@router.get("", response_model=TaskPage, summary="List tasks")
def list_tasks(
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority: Annotated[Priority | None, Query()] = None,
    q: Annotated[str | None, Query(min_length=2, max_length=60)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Return a filtered, paginated page of tasks.

    The parameter is named status_filter in Python because `status` shadows the
    imported fastapi.status module. The alias keeps the public name correct, so
    the API is unaffected by a local naming problem.
    """
    results = store.list()
    if status_filter is not None:
        results = [t for t in results if t["status"] == status_filter]
    if priority is not None:
        results = [t for t in results if t["priority"] == priority]
    if q is not None:
        needle = q.casefold()
        results = [t for t in results if needle in t["title"].casefold()]

    total = len(results)
    page = results[offset : offset + limit]
    return {"total": total, "count": len(page), "limit": limit, "offset": offset, "items": page}


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED, summary="Create a task")
def create_task(payload: TaskCreate) -> dict:
    """Create a task.

    A duplicate title is a 409 rather than a silent second row. Whether that is
    right depends on the domain; here it exists so there is a conflict path to
    test on create.
    """
    if store.find_by_title(payload.title):
        raise ConflictError(
            f"A task titled {payload.title!r} already exists",
            details=[{"field": "body.title", "message": "must be unique", "type": "duplicate"}],
        )
    task = store.create(payload.model_dump())
    logger.info("created task %s", task["id"])
    return task


@router.get("/{task_id}", response_model=TaskRead, summary="Get one task")
def get_task(task_id: TaskId) -> dict:
    """Return a single task."""
    return _require(task_id)


@router.put("/{task_id}", response_model=TaskRead, summary="Replace a task")
def replace_task(task_id: TaskId, payload: TaskReplace) -> dict:
    """Replace a task entirely.

    Every field the client omits reverts to its default rather than being kept.
    Sending the same request twice leaves the same state, which is what makes
    PUT idempotent.
    """
    _require(task_id)
    return store.replace(task_id, payload.model_dump())


@router.patch("/{task_id}", response_model=TaskRead, summary="Update a task")
def update_task(task_id: TaskId, payload: TaskUpdate) -> dict:
    """Update only the fields the client sent."""
    _require(task_id)
    changes = payload.model_dump(exclude_unset=True)
    return store.update(task_id, changes)


@router.post("/{task_id}/complete", response_model=TaskRead, summary="Mark a task done")
def complete_task(task_id: TaskId) -> dict:
    """Move a task to done.

    A state transition rather than a field edit, so it gets its own endpoint.
    Completing an already-complete task is a 409: the request is well-formed but
    incompatible with the current state.
    """
    task = _require(task_id)
    if task["status"] == TaskStatus.DONE:
        raise ConflictError(f"Task {task_id} is already done")
    return store.update(task_id, {"status": TaskStatus.DONE})


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a task")
def delete_task(task_id: TaskId) -> None:
    """Delete a task."""
    _require(task_id)
    store.delete(task_id)
