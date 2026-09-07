"""Logging setup, with the request id injected into every record.

The filter is the point of this file. Rather than every log call remembering to
include the id, a filter reads it from the ContextVar and adds it to the record,
so the format string can reference it and every line is correlated automatically.
"""

import logging
import sys

from context import get_request_id


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every log record.

    A Filter that always returns True is not filtering, it is decorating. This
    is the documented way to add computed fields to records without wrapping
    every logger call.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once, at startup."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    handler.addFilter(RequestIdFilter())

    # force=True replaces the handlers uvicorn installs. Without it basicConfig
    # finds the root logger already configured and silently does nothing.
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)

    # The http client used by the tests logs every request at INFO, which
    # drowns out the output being demonstrated.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
