"""Admin routes, guarded by a router-level dependency.

No endpoint in this file mentions the API key. The guard is declared once on
the router, so a route added later is protected by default rather than by
whoever adds it remembering. That default is the whole reason to attach it at
the router rather than to each endpoint.
"""

from fastapi import APIRouter, Depends

from dependencies import Pagination, StoreDep, verify_api_key
from schemas import ERROR_RESPONSES, TaskPage

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(verify_api_key)],
    responses={**ERROR_RESPONSES, 401: {"description": "Missing or invalid API key"}},
)


@router.get("/tasks", response_model=TaskPage, summary="List every task, unfiltered")
def admin_list_tasks(store: StoreDep, page: Pagination) -> dict:
    """Fourth consumer of the pagination dependency, in a different router."""
    return page.page_of(store.list())


@router.get("/stats", summary="Counts by status and priority")
def admin_stats(store: StoreDep) -> dict:
    """Aggregate counts. Protected without saying so anywhere in this function."""
    tasks = store.list()
    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for task in tasks:
        by_status[task["status"]] = by_status.get(task["status"], 0) + 1
        by_priority[task["priority"]] = by_priority.get(task["priority"], 0) + 1
    return {"total": len(tasks), "by_status": by_status, "by_priority": by_priority}
