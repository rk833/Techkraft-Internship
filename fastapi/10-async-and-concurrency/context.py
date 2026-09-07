"""Per-request context.

A ContextVar holds the current request id. Anything running inside the request -
an endpoint, a service function, a log filter - can read it without the id being
threaded through every function signature as an argument.

ContextVar rather than a module-level global because a global is shared across
concurrent requests. ContextVar is per-task, so two requests being served at the
same time see their own value.
"""

from contextvars import ContextVar

# The default matters: log records emitted at startup, before any request
# exists, still need something to render.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the current request id, or "-" outside a request."""
    return request_id_ctx.get()
