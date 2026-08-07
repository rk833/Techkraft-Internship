"""Logging setup.

Deliberately minimal. Structured JSON logging and log shipping belong with the
deployment work in module 16; what matters here is that an unhandled exception
leaves a traceback somewhere the operator can find, tagged with the same
reference the client was given.
"""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once, at startup.

    force=True replaces any handler uvicorn already installed. Without it,
    calling basicConfig after uvicorn has started is a no-op, and the level set
    here would silently have no effect.
    """
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
