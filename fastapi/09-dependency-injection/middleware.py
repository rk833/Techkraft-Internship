"""Custom middleware.

RequestContextMiddleware is written as pure ASGI rather than as a subclass of
BaseHTTPMiddleware. The reason is the ContextVar: BaseHTTPMiddleware runs the
downstream application in a separate anyio task, so a ContextVar set in the
middleware before calling call_next is not reliably visible to the endpoint.
Pure ASGI middleware runs in the same task, so the value propagates.

A pure ASGI middleware is a callable taking (scope, receive, send). To change a
response header it wraps send and edits the http.response.start message on the
way out, because by the time the response object exists it is already streaming.
"""

import logging
import re
import time
import uuid
from typing import Awaitable, Callable

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from context import request_id_ctx

logger = logging.getLogger("api.request")

REQUEST_ID_HEADER = "x-request-id"
RESPONSE_TIME_HEADER = "x-response-time-ms"

# An inbound request id is echoed back in a response header, so it cannot be
# trusted blindly. Anything outside this pattern is discarded and replaced,
# which prevents header injection and unbounded values in the logs.
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def resolve_request_id(headers: dict[bytes, bytes]) -> str:
    """Use the client's request id when it is safe, otherwise generate one.

    Honouring an inbound id is what lets a trace span several services: a
    gateway assigns it once and every service downstream logs the same value.
    """
    incoming = headers.get(REQUEST_ID_HEADER.encode())
    if incoming:
        candidate = incoming.decode("latin-1", errors="ignore")
        if SAFE_REQUEST_ID.match(candidate):
            return candidate
    return uuid.uuid4().hex[:12]


ErrorHandler = Callable[[Request, Exception], Awaitable[Response]]


class RequestContextMiddleware:
    """Assign a request id, time the request, log the outcome, and catch anything
    that escaped the router.

    The last of those is not optional decoration. Starlette's ServerErrorMiddleware
    sits OUTSIDE every user middleware, so a 500 it generates never passes back
    through this class or through CORSMiddleware. Left alone, that means an
    unhandled exception produces a response with no request id, no timing header
    and - critically - no CORS headers, which a browser reports as an opaque CORS
    failure instead of showing the actual error.

    Catching here instead means the error response is produced inside the stack
    and travels out through every layer like any other response.
    """

    def __init__(self, app: ASGIApp, on_unhandled: ErrorHandler | None = None) -> None:
        self.app = app
        self.on_unhandled = on_unhandled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Lifespan and websocket scopes pass straight through. A middleware that
        # assumes every scope is http breaks startup in a confusing way.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        request_id = resolve_request_id(headers)
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_started = True
                elapsed_ms = (time.perf_counter() - start) * 1000
                # MutableHeaders edits the raw header list in place. Setting the
                # headers here rather than on a Response object is what makes
                # this work for streaming and file responses too.
                out = MutableHeaders(scope=message)
                out[REQUEST_ID_HEADER] = request_id
                out[RESPONSE_TIME_HEADER] = f"{elapsed_ms:.2f}"
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception as exc:
            # Once headers are on the wire a second response cannot be sent, so
            # the only correct move is to let it propagate and have the server
            # drop the connection.
            if response_started or self.on_unhandled is None:
                raise
            response = await self.on_unhandled(Request(scope, receive), exc)
            await response(scope, receive, send_with_headers)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "%s %s -> %s in %.2fms",
                scope["method"],
                scope["path"],
                status_code,
                elapsed_ms,
            )
            # Resetting keeps the ContextVar from leaking into whatever task
            # reuses this context next.
            request_id_ctx.reset(token)


def add_security_headers_middleware(app) -> None:
    """Register a decorator-style middleware for static security headers.

    The @app.middleware("http") decorator is BaseHTTPMiddleware underneath. It
    is the simplest form and it is the right choice when all that is needed is
    to inspect or decorate a finished response, as here. Its limitations only
    bite for ContextVars and for streaming bodies.
    """

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
