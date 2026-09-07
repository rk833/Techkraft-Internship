"""Task schemas and the error envelope carried forward from module 06."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from errors import ErrorCode


class ErrorDetail(BaseModel):
    """One specific thing that was wrong."""

    field: str | None = None
    message: str
    type: str | None = None


class ErrorBody(BaseModel):
    """The contents of the error envelope."""

    code: ErrorCode
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
    reference: str


class ErrorResponse(BaseModel):
    """Every failure from this API looks like this."""

    error: ErrorBody


class TaskStatus(str, Enum):
    """Where a task is in its lifecycle."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Priority(str, Enum):
    """How urgent a task is."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskBase(BaseModel):
    """Fields shared by input and output."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    priority: Priority = Priority.MEDIUM
    tags: list[str] = Field(default_factory=list, max_length=10)


class TaskCreate(TaskBase):
    """A new task. Status is not accepted - every task starts as todo."""


class TaskReplace(TaskBase):
    """A full replacement via PUT.

    Status is accepted here because PUT replaces the whole resource, so the
    client has to be able to state what the status should become.
    """

    status: TaskStatus = TaskStatus.TODO


class TaskUpdate(BaseModel):
    """A partial update via PATCH. Every field optional."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    priority: Priority | None = None
    status: TaskStatus | None = None
    tags: list[str] | None = Field(default=None, max_length=10)


class TaskRead(BaseModel):
    """A task as returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: Priority
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class TaskPage(BaseModel):
    """A page of tasks, with the total before slicing."""

    total: int
    count: int
    limit: int
    offset: int
    items: list[TaskRead]


ERROR_RESPONSES: dict[int | str, dict] = {
    404: {"model": ErrorResponse, "description": "Not found"},
    409: {"model": ErrorResponse, "description": "Conflict with existing state"},
    422: {"model": ErrorResponse, "description": "Validation failed"},
    500: {"model": ErrorResponse, "description": "Unhandled server error"},
}
