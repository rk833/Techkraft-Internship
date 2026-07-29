"""
Shared model construction, with automatic fallback when quota runs out.

The Gemini free tier allows 20 requests per day, counted per model, per
project. That is easy to exhaust while working through a module, so this module
keeps a list of candidates and moves to the next one when the current
combination is used up.

Configuration lives in .env at the repository root:

    GOOGLE_API_KEY            the main key
    GOOGLE_API_KEYS           optional, comma separated, additional keys
    GEMINI_MODEL              the model to prefer
    GEMINI_FALLBACK_MODELS    optional, comma separated, tried in order after it
    GEMINI_THINKING_BUDGET    0 to disable reasoning, empty to omit the setting

Each key must come from a separate Google Cloud project, because the quota is
counted per project. Creating extra projects under one account is the supported
way to do this.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from .errors import ConfigError, is_bad_argument, is_quota_exhausted

# .env sits at the repository root, one level above this package, so it is
# found no matter which module folder a script is run from
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_MODEL = "gemini-3.5-flash"


def _split(raw: str) -> list:
    """Parse a comma separated setting, dropping blanks and duplicates."""
    seen = []
    for item in raw.split(","):
        item = item.strip()
        if item and item not in seen:
            seen.append(item)
    return seen


def api_keys() -> list:
    """All configured keys, primary first."""
    keys = _split(os.getenv("GOOGLE_API_KEY", ""))
    for key in _split(os.getenv("GOOGLE_API_KEYS", "")):
        if key not in keys:
            keys.append(key)

    if not keys:
        raise ConfigError(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return keys


def model_names() -> list:
    """The preferred model, then any fallbacks."""
    names = _split(os.getenv("GEMINI_MODEL", "") or DEFAULT_MODEL)
    for name in _split(os.getenv("GEMINI_FALLBACK_MODELS", "")):
        if name not in names:
            names.append(name)
    return names


def thinking_budget():
    """
    The configured reasoning budget, or None to leave the setting off.

    0 disables the model's internal reasoning step, which otherwise spends
    output tokens before the answer starts. Several models reject the parameter
    outright, so it has to be omittable.
    """
    raw = os.getenv("GEMINI_THINKING_BUDGET", "0").strip()
    return int(raw) if raw else None


def build_model(
    model: str,
    api_key: str,
    temperature: float = 0.7,
    max_output_tokens: int = 512,
    with_thinking: bool = True,
):
    """Create one configured chat model."""
    settings = dict(
        model=model,
        google_api_key=api_key,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

    budget = thinking_budget()
    if with_thinking and budget is not None:
        settings["thinking_budget"] = budget

    return ChatGoogleGenerativeAI(**settings)


def _attempts(**model_kwargs):
    """
    Every combination worth trying, in order.

    Models rotate within a key before moving to the next key, since each model
    has its own daily allowance.
    """
    for key in api_keys():
        for name in model_names():
            yield name, key, model_kwargs


def run_with_fallback(action, verbose: bool = True, **model_kwargs):
    """
    Run action(model) against the first combination that has quota left.

    action receives a configured model and returns whatever it likes, so this
    works for invoke, structured output, and chains.

    Only quota exhaustion triggers a move to the next candidate. Everything
    else is raised, because retrying a different model would hide the real
    problem. A model that rejects thinking_budget is retried once without it.
    """
    last_error = None
    last_model = model_names()[0]

    for name, key, kwargs in _attempts(**model_kwargs):
        last_model = name
        for with_thinking in (True, False):
            try:
                return action(build_model(name, key, with_thinking=with_thinking, **kwargs))
            except Exception as error:
                last_error = error
                if is_bad_argument(error) and with_thinking and thinking_budget() is not None:
                    # this model does not accept thinking_budget, drop it and retry
                    continue
                if is_quota_exhausted(error):
                    if verbose:
                        print(f"[{name} is out of quota, trying the next model]")
                    break
                raise

    raise last_error if last_error else ConfigError("no model candidates configured")


async def arun_with_fallback(action, verbose: bool = True, **model_kwargs):
    """
    Async twin of run_with_fallback, where action is a coroutine function.

    Needed because MCP tools and FastAPI handlers are async. Wrapping the sync
    version in asyncio.run from inside a running event loop raises
    "asyncio.run() cannot be called from a running event loop", so the await
    has to happen here rather than being bridged.
    """
    last_error = None

    for name, key, kwargs in _attempts(**model_kwargs):
        for with_thinking in (True, False):
            try:
                return await action(
                    build_model(name, key, with_thinking=with_thinking, **kwargs)
                )
            except Exception as error:
                last_error = error
                if is_bad_argument(error) and with_thinking and thinking_budget() is not None:
                    continue
                if is_quota_exhausted(error):
                    if verbose:
                        print(f"[{name} is out of quota, trying the next model]")
                    break
                raise

    raise last_error if last_error else ConfigError("no model candidates configured")


def stream_with_fallback(payload, verbose: bool = True, **model_kwargs):
    """
    Same idea as run_with_fallback, for streaming.

    The first chunk has to be pulled inside the try block, because that is when
    a quota error surfaces. Later chunks are yielded straight through.
    """
    last_error = None

    for name, key, kwargs in _attempts(**model_kwargs):
        for with_thinking in (True, False):
            try:
                model = build_model(name, key, with_thinking=with_thinking, **kwargs)
                chunks = iter(model.stream(payload))
                first = next(chunks)
            except StopIteration:
                return
            except Exception as error:
                last_error = error
                if is_bad_argument(error) and with_thinking and thinking_budget() is not None:
                    continue
                if is_quota_exhausted(error):
                    if verbose:
                        print(f"[{name} is out of quota, trying the next model]")
                    break
                raise

            yield first
            yield from chunks
            return

    raise last_error if last_error else ConfigError("no model candidates configured")


def active_model_name() -> str:
    """The model that will be tried first. Used for error messages."""
    return model_names()[0]
