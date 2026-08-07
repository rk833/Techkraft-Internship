"""Application error types.

One base class, a small set of subclasses, and a stable machine-readable code
per failure. Handlers in handlers.py turn any of these into the single response
envelope defined in schemas.py.

Nothing in this file knows about FastAPI. These are plain exceptions, so the
same types can be raised from a service layer or a repository that has no
business importing a web framework.
"""

from enum import Enum


class ErrorCode(str, Enum):
    """Stable machine-readable failure codes.

    Clients branch on these, not on the human-readable message. The message can
    be reworded or translated at any time; the code is part of the contract and
    changing one is a breaking change.
    """

    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    VALIDATION_ERROR = "validation_error"
    INVALID_REQUEST = "invalid_request"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    INTERNAL_ERROR = "internal_error"


class AppError(Exception):
    """Base class for every error this application raises deliberately.

    Carrying the status code on the exception rather than at the raise site
    means a NotFoundError is a 404 everywhere, and cannot become a 400 in one
    handler because someone typed the wrong number.
    """

    status_code: int = 500
    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    message: str = "An unexpected error occurred"

    def __init__(self, message: str | None = None, details: list[dict] | None = None) -> None:
        self.message = message or self.message
        self.details = details or []
        super().__init__(self.message)


class NotFoundError(AppError):
    """A well-formed request for something that does not exist."""

    status_code = 404
    code = ErrorCode.NOT_FOUND
    message = "Resource not found"


class ConflictError(AppError):
    """The request is valid but conflicts with existing state."""

    status_code = 409
    code = ErrorCode.CONFLICT
    message = "Request conflicts with the current state"


class ValidationRuleError(AppError):
    """A rule FastAPI cannot check from a signature.

    Deliberately shares the 422 status and the validation_error code with
    FastAPI's own validation failures, so a client has one code path for
    "your input was unacceptable" rather than two.
    """

    status_code = 422
    code = ErrorCode.VALIDATION_ERROR
    message = "Request failed validation"


class UpstreamError(AppError):
    """A dependency this service needs is unavailable.

    503 rather than 500: the fault is not in this service, and the condition is
    expected to be temporary, which tells a client that retrying is reasonable.
    """

    status_code = 503
    code = ErrorCode.UPSTREAM_UNAVAILABLE
    message = "An upstream service is unavailable"
