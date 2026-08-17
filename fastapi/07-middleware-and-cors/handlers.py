"""Exception handlers, carried over from module 06 with one change.

The reference is no longer generated here. It is read from the ContextVar that
middleware set for this request, so the id in an error body is the same id in
the X-Request-ID header and in every log line for that request.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import get_settings
from context import get_request_id
from errors import AppError, ErrorCode
from schemas import ErrorBody, ErrorDetail, ErrorResponse

logger = logging.getLogger("api.errors")

STATUS_TO_CODE: dict[int, ErrorCode] = {
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
    503: ErrorCode.UPSTREAM_UNAVAILABLE,
}


def build_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    details: list[ErrorDetail] | None = None,
) -> JSONResponse:
    """Serialise the one and only error envelope."""
    payload = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or [],
            reference=get_request_id(),
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    """Handle anything raised deliberately by this application."""
    level = logging.WARNING if exc.status_code < 500 else logging.ERROR
    logger.log(level, "%s -> %s %s: %s", request.url.path, exc.status_code, exc.code.value, exc.message)
    return build_response(exc.status_code, exc.code, exc.message, [ErrorDetail(**d) for d in exc.details])


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Reshape FastAPI's automatic 422 into our envelope."""
    details = [
        ErrorDetail(
            field=".".join(str(part) for part in error["loc"]),
            message=error["msg"],
            type=error["type"],
        )
        for error in exc.errors()
    ]
    logger.info("%s -> 422 validation_error, %d problem(s)", request.url.path, len(details))
    return build_response(422, ErrorCode.VALIDATION_ERROR, "The request failed validation", details)


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Normalise HTTPException, including the ones Starlette raises itself."""
    code = STATUS_TO_CODE.get(exc.status_code, ErrorCode.INVALID_REQUEST)
    message = exc.detail if isinstance(exc.detail, str) else "Request could not be processed"
    logger.warning("%s -> %s %s", request.url.path, exc.status_code, code.value)
    return build_response(exc.status_code, code, message)


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Last resort for anything not raised on purpose."""
    logger.exception("%s -> 500 internal_error, unhandled %s", request.url.path, type(exc).__name__)
    settings = get_settings()
    details: list[ErrorDetail] = []
    if settings.debug and not settings.is_production:
        # The exception TYPE only, never str(exc). A contract test in module 08
        # showed the message leaking a postgres:// connection string.
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
        details,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach every handler to the application."""
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)
