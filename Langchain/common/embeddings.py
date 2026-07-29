"""
Shared embedding model construction, with the same quota fallback as chat.

Embeddings have their own free tier allowance, separate from the chat models,
so exhausting one does not affect the other.

Configuration in .env:

    GEMINI_EMBEDDING_MODEL            preferred embedding model
    GEMINI_EMBEDDING_FALLBACK_MODELS  comma separated, tried in order after it
    GEMINI_EMBEDDING_DIM             optional, truncate vectors to this size
"""

import os

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from .errors import ConfigError, is_quota_exhausted
from .models import _split, api_keys

DEFAULT_EMBEDDING_MODEL = "models/gemini-embedding-001"


def _qualify(name: str) -> str:
    """The API expects embedding models to be named models/<name>."""
    return name if name.startswith("models/") else f"models/{name}"


def embedding_model_names() -> list:
    """The preferred embedding model, then any fallbacks."""
    names = _split(os.getenv("GEMINI_EMBEDDING_MODEL", "") or DEFAULT_EMBEDDING_MODEL)
    for name in _split(os.getenv("GEMINI_EMBEDDING_FALLBACK_MODELS", "")):
        if name not in names:
            names.append(name)
    return [_qualify(n) for n in names]


def embedding_dimension():
    """Configured vector size, or None for the model's default."""
    raw = os.getenv("GEMINI_EMBEDDING_DIM", "").strip()
    return int(raw) if raw else None


def build_embeddings(model: str, api_key: str, task_type: str = None):
    """
    Create one configured embedding model.

    task_type tells the model what the text will be used for. Gemini produces
    different vectors for a search query than for a stored document, and using
    the right one measurably improves retrieval. Leaving it unset is fine when
    simply comparing two pieces of text.
    """
    settings = dict(model=model, google_api_key=api_key)

    dimension = embedding_dimension()
    if dimension:
        settings["output_dimensionality"] = dimension
    if task_type:
        settings["task_type"] = task_type

    return GoogleGenerativeAIEmbeddings(**settings)


def embed_with_fallback(action, task_type: str = None, verbose: bool = True):
    """
    Run action(embeddings) against the first model and key that has quota left.

    Mirrors run_with_fallback in models.py. Only quota exhaustion moves on to
    the next candidate; every other error is raised, so real problems are not
    hidden behind a retry.
    """
    last_error = None

    for key in api_keys():
        for name in embedding_model_names():
            try:
                return action(build_embeddings(name, key, task_type=task_type))
            except Exception as error:
                last_error = error
                if is_quota_exhausted(error):
                    if verbose:
                        print(f"[{name} is out of quota, trying the next model]")
                    continue
                raise

    raise last_error if last_error else ConfigError("no embedding models configured")


def active_embedding_model() -> str:
    """The embedding model that will be tried first. Used in error messages."""
    return embedding_model_names()[0]
