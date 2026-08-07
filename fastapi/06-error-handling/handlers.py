"""Exception handlers.

Four handlers, covering every way this application can fail. Together they
guarantee that no matter what goes wrong, the client receives the same envelope
and never receives a stack trace.

Registration order does not matter; Starlette dispatches on exception type,
picking the most specific registered handler for the raised class.
"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import get_settings
from errors import AppError, ErrorCode
from schemas import ErrorBody, ErrorDetail, ErrorResponse

logger = logging.getLogger("api.errors")

# Maps the status codes Starlette raises internally onto our own codes, so a
# 404 from an unmatched route is indistinguishable from a 404 we raised.
STATUS_TO_CODE: dict[int, ErrorCode] = {
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
    503: ErrorCode.UPSTREAM_UNAVAILABLE,
}


def new_reference() -> str:
    """Return a short opaque id shared between the response and the log line.

    Module 07 replaces this with a per-request id assigned in middleware, so
    every request has one rather than only the failing ones.
    """
    return uuid.uuid4().hex[:12]


def build_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    reference: str,
    details: list[ErrorDetail] | None = None,
) -> JSONResponse:
    """Serialise the one and only error envelope.

    Every handler goes through here. That is the mechanism that makes the shape
    consistent - not a convention that each handler is trusted to follow.
    """
    payload = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or [],
            reference=reference,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers={"X-Error-Reference": reference},
    )


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    """Handle anything raised deliberately by this application."""
    reference = new_reference()
    # Client errors are informational; a 5xx we raised ourselves is a real
    # problem and deserves a louder level.
    level = logging.WARNING if exc.status_code < 500 else logging.ERROR
    logger.log(
        level,
        "%s %s -> %s %s [ref=%s] %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.code.value,
        reference,
        exc.message,
    )
    details = [ErrorDetail(**d) for d in exc.details]
    return build_response(exc.status_code, exc.code, exc.message, reference, details)


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Reshape FastAPI's automatic 422 into our envelope.

    Without this handler, automatic validation failures return a bare
    {"detail": [...]} list while our own errors return the envelope, and a
    client has to handle two unrelated shapes. This is the inconsistency that
    has been present since module 03.

    Pydantic's loc is a tuple like ("query", "limit") or ("body", "items", 0,
    "sku"). Joining it produces a dotted path a client can map to an input.
    """
    details = [
        ErrorDetail(
            field=".".join(str(part) for part in error["loc"]),
            message=error["msg"],
            type=error["type"],
        )
        for error in exc.errors()
    ]
    reference = new_reference()
    logger.info(
        "%s %s -> 422 validation_error [ref=%s] %d problem(s)",
        request.method,
        request.url.path,
        reference,
        len(details),
    )
    return build_response(
        422,
        ErrorCode.VALIDATION_ERROR,
        "The request failed validation",
        reference,
        details,
    )


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Normalise HTTPException, including the ones Starlette raises itself.

    An unmatched route and an unsupported method never reach our code - the
    router raises before any endpoint is chosen. Without this handler those
    responses would be bare {"detail": "Not Found"} objects, so the envelope
    would hold for every path except the ones a confused client is most likely
    to hit.
    """
    reference = new_reference()
    code = STATUS_TO_CODE.get(exc.status_code, ErrorCode.INVALID_REQUEST)
    message = exc.detail if isinstance(exc.detail, str) else "Request could not be processed"
    logger.warning(
        "%s %s -> %s %s [ref=%s]",
        request.method,
        request.url.path,
        exc.status_code,
        code.value,
        reference,
    )
    return build_response(exc.status_code, code, message, reference, None)


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Last resort for anything not raised on purpose.

    This is the handler that matters for security. The client gets a fixed
    message and a reference; the traceback goes to the log and nowhere else.
    """
    reference = new_reference()
    # logger.exception attaches the full traceback to the log record. This is
    # the only place the traceback exists, and it never touches the response.
    logger.exception(
        "%s %s -> 500 internal_error [ref=%s] unhandled %s",
        request.method,
        request.url.path,
        reference,
        type(exc).__name__,
    )

    settings = get_settings()
    details: list[ErrorDetail] = []
    if settings.debug and not settings.is_production:
        # The exception TYPE only, never str(exc).
        #
        # This originally included the exception message as a "deliberate
        # development trade". A contract test in module 08 then demonstrated it
        # leaking a full postgres://user:pw@host/db connection string, because
        # that is what the exception message happened to contain. Exception
        # messages routinely carry credentials, SQL fragments and file paths,
        # and there is no way to know in advance which ones do.
        #
        # The type name alone is safe: it is a fixed identifier with nothing
        # interpolated into it.
        details = [
            ErrorDetail(
                field=None,
                message=f"Unhandled {type(exc).__name__}. The traceback is in the server log.",
                type=type(exc).__name__,
            )
        ]

    return build_response(
        500,
        ErrorCode.INTERNAL_ERROR,
        "An unexpected error occurred. Quote the reference when reporting it.",
        reference,
        details,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach every handler to the application."""
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)
