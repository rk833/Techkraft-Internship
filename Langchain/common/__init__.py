"""
Shared helpers used by every module.

Only boilerplate lives here: error explanation and the quota fallback logic.
Anything that is actually part of a module's lesson stays in that module's own
file, so each project can still be read on its own.
"""

import sys

# Models routinely emit curly quotes, dashes and accented characters. The
# Windows console defaults to cp1252, which cannot encode them, so titles come
# out mangled or the print raises UnicodeEncodeError. Switching the streams to
# UTF-8 fixes it for every module at once.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from .errors import ConfigError, describe_api_error
from .embeddings import (
    active_embedding_model,
    build_embeddings,
    embed_with_fallback,
    embedding_model_names,
)
from .models import (
    active_model_name,
    arun_with_fallback,
    build_model,
    model_names,
    run_with_fallback,
    stream_with_fallback,
)

__all__ = [
    "ConfigError",
    "describe_api_error",
    "active_model_name",
    "arun_with_fallback",
    "build_model",
    "model_names",
    "run_with_fallback",
    "stream_with_fallback",
    "active_embedding_model",
    "build_embeddings",
    "embed_with_fallback",
    "embedding_model_names",
]
