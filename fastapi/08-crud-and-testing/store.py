"""In-memory task store.

Written as a class with an explicit reset() rather than as module-level dicts.
That single decision is what makes the test suite order-independent: a fixture
can restore a known state before every test without reaching into globals or
reimporting modules.

The interface is deliberately the shape a repository would have against a real
database, so module 11 replaces the body of each method rather than rewriting
every caller.
"""

from datetime import datetime, timezone

from schemas import Priority, TaskStatus


def _now() -> datetime:
    """Current UTC time. One place to patch if a test ever needs a fixed clock."""
    return datetime.now(timezone.utc)


SEED_TASKS: list[dict] = [
    {"title": "Write the module 08 README", "description": "Cover CRUD and pytest.",
     "status": TaskStatus.IN_PROGRESS, "priority": Priority.HIGH, "tags": ["docs", "fastapi"]},
    {"title": "Review pull request", "description": None,
     "status": TaskStatus.TODO, "priority": Priority.MEDIUM, "tags": ["review"]},
    {"title": "Renew domain", "description": "Expires in March.",
     "status": TaskStatus.TODO, "priority": Priority.LOW, "tags": []},
    {"title": "Fix the timing header", "description": "Was reporting negative values.",
     "status": TaskStatus.DONE, "priority": Priority.HIGH, "tags": ["bug", "fastapi"]},
]


class TaskStore:
    """A dict-backed task repository."""

    def __init__(self) -> None:
        self._tasks: dict[int, dict] = {}
        self._next_id = 1
        self.reset()

    def reset(self) -> None:
        """Restore the store to its seeded starting state.

        Called by an autouse test fixture. Without it, a test that creates a
        task changes what a later test sees, and the suite only passes in the
        order it happened to be written in.
        """
        self._tasks = {}
        self._next_id = 1
        for seed in SEED_TASKS:
            self.create(dict(seed))

    def create(self, fields: dict) -> dict:
        """Insert a task and return it."""
        now = _now()
        task = {
            "id": self._next_id,
            "status": TaskStatus.TODO,
            "created_at": now,
            "updated_at": now,
            **fields,
        }
        self._tasks[task["id"]] = task
        self._next_id += 1
        return task

    def get(self, task_id: int) -> dict | None:
        """Return one task, or None."""
        return self._tasks.get(task_id)

    def list(self) -> list[dict]:
        """Return every task, oldest first."""
        return sorted(self._tasks.values(), key=lambda t: t["id"])

    def replace(self, task_id: int, fields: dict) -> dict:
        """Overwrite a task, preserving only its id and creation time."""
        existing = self._tasks[task_id]
        task = {
            "id": task_id,
            "created_at": existing["created_at"],
            "updated_at": _now(),
            **fields,
        }
        self._tasks[task_id] = task
        return task

    def update(self, task_id: int, changes: dict) -> dict:
        """Merge changes into a task."""
        task = self._tasks[task_id]
        task.update(changes)
        task["updated_at"] = _now()
        return task

    def delete(self, task_id: int) -> None:
        """Remove a task."""
        del self._tasks[task_id]

    def exists(self, task_id: int) -> bool:
        """True when the task is present."""
        return task_id in self._tasks

    def find_by_title(self, title: str) -> dict | None:
        """Return the task with this exact title, or None."""
        return next((t for t in self._tasks.values() if t["title"] == title), None)


# One instance for the running application. Tests reset it rather than
# replacing it, so no import anywhere needs to know about the test suite.
store = TaskStore()
