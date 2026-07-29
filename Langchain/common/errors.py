"""
Shared error handling.

The raw provider error for something ordinary, such as a quota limit, is around
sixty lines of nested JSON wrapped in a traceback. These helpers classify the
error and produce a short message that says what to do about it.
"""


class ConfigError(Exception):
    """Raised for problems the user can fix in .env, such as a missing key."""


def _cause(error: Exception) -> Exception:
    """langchain wraps the provider error, so the original is on __cause__."""
    return error.__cause__ or error


def is_quota_exhausted(error: Exception) -> bool:
    """
    True when the daily free tier allowance for this model is used up.

    This is the case worth rotating away from, because waiting will not help
    until the quota resets. A per minute rate limit is a different situation
    and is not reported here.
    """
    text = str(_cause(error))
    return "RESOURCE_EXHAUSTED" in text and ("PerDay" in text or "limit: 0" in text)


def is_rate_limited(error: Exception) -> bool:
    """True for a per minute rate limit, which usually clears on its own."""
    text = str(_cause(error))
    return "RESOURCE_EXHAUSTED" in text and not is_quota_exhausted(error)


def is_bad_argument(error: Exception) -> bool:
    """True when the model rejected a request setting, such as thinking_budget."""
    cause = _cause(error)
    return getattr(cause, "code", None) == 400 or "INVALID_ARGUMENT" in str(cause)


def is_model_missing(error: Exception) -> bool:
    """True when the model name is unknown or has been retired."""
    cause = _cause(error)
    return getattr(cause, "code", None) == 404 or "NOT_FOUND" in str(cause)


def describe_api_error(error: Exception, model: str) -> str:
    """Turn a provider error into a short explanation with a suggested fix."""
    cause = _cause(error)
    code = getattr(cause, "code", None)
    text = str(cause)

    if is_quota_exhausted(error):
        if "limit: 0" in text:
            return (
                f"Model '{model}' has no free tier quota on this API key "
                f"(the reported limit is 0).\n"
                f"Older models are often dropped from the free tier entirely.\n"
                f"Run 'python 01-Models/list_models.py --probe' to find one that "
                f"works, then set GEMINI_MODEL in .env."
            )
        return (
            f"Daily free tier quota used up for every model and key that was "
            f"tried, most recently '{model}'.\n"
            f"The cap is 20 requests per day, per model, per project.\n"
            f"Add more names to GEMINI_FALLBACK_MODELS, or more keys to "
            f"GOOGLE_API_KEYS, in .env. See the root README.\n"
            f"Otherwise the quota resets at midnight Pacific time."
        )

    if is_rate_limited(error):
        return (
            "Per minute rate limit reached. Wait a minute and try again.\n"
            "Modes that make several calls in a row hit this first."
        )

    if is_model_missing(error):
        return (
            f"Model '{model}' was not found or is no longer served.\n"
            f"A model can appear in list_models.py and still be retired.\n"
            f"Run 'python 01-Models/list_models.py --probe' to find one that "
            f"works, then set GEMINI_MODEL in .env."
        )

    if is_bad_argument(error):
        return (
            f"Model '{model}' rejected one of the request settings.\n"
            f"The usual cause is thinking_budget, which several models do not "
            f"accept.\n"
            f"Set GEMINI_THINKING_BUDGET= (empty) in .env to stop sending it."
        )

    if code in (401, 403) or "PERMISSION_DENIED" in text or "API_KEY_INVALID" in text:
        return (
            "The API key was rejected. Check GOOGLE_API_KEY in .env, or create a "
            "new key at https://aistudio.google.com/apikey"
        )

    return f"Call to model '{model}' failed: {text}"
