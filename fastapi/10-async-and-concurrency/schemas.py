"""The error envelope, carried forward from module 06.

This module has no resource schemas of its own - the aggregator returns
assembled upstream payloads whose shape belongs to the upstream services.
"""

from pydantic import BaseModel, Field

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


ERROR_RESPONSES: dict[int | str, dict] = {
    422: {"model": ErrorResponse, "description": "Validation failed"},
    500: {"model": ErrorResponse, "description": "Unhandled server error"},
    503: {"model": ErrorResponse, "description": "Upstream dependency unavailable"},
    504: {"model": ErrorResponse, "description": "Upstream timed out"},
}
