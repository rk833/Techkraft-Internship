"""Password hashing and token handling.

Deliberately free of FastAPI imports. These are the primitives; the HTTP
concerns - which status code, which header - live in dependencies.py.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt

from app.config import Settings, get_settings

logger = logging.getLogger("api.security")

TokenType = Literal["access", "refresh"]

# bcrypt operates on at most 72 bytes and, since version 4, raises rather than
# silently truncating. Enforced in the schema so a long password is a 422 and
# not a 500 - and so two passwords sharing a 72-byte prefix can never be
# treated as the same password.
MAX_PASSWORD_BYTES = 72

# A hash that no password can ever produce, because a real bcrypt hash begins
# with $2b$. Used as the stored value for accounts that must not be able to log
# in, and as the dummy target for the timing defence below.
UNUSABLE_PASSWORD = "!"

# A real hash of a throwaway value, computed once. verify_password() runs
# against this when the user does not exist, so a failed login costs the same
# whether the username was wrong or the password was.
_DUMMY_HASH: bytes | None = None


def _dummy_hash(settings: Settings) -> bytes:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt(settings.bcrypt_rounds))
    return _DUMMY_HASH


def hash_password(password: str, settings: Settings | None = None) -> str:
    """Hash a password with a fresh random salt.

    bcrypt generates and embeds the salt itself, so the same password hashed
    twice produces two different strings. That is what defeats rainbow tables,
    and it is why there is no separate salt column.

    The cost factor is stored inside the hash, so raising it later does not
    invalidate existing hashes - they simply verify at their original cost.
    """
    settings = settings or get_settings()
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password exceeds {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(settings.bcrypt_rounds)).decode("utf-8")


def verify_password(password: str, hashed: str | None, settings: Settings | None = None) -> bool:
    """Check a password against a stored hash.

    When `hashed` is missing or unusable, a dummy verification still runs.
    Returning early instead would make a nonexistent username measurably faster
    than a wrong password, which lets an attacker enumerate valid accounts
    without ever logging in.
    """
    settings = settings or get_settings()
    encoded = password.encode("utf-8")[:MAX_PASSWORD_BYTES]

    if not hashed or hashed == UNUSABLE_PASSWORD:
        bcrypt.checkpw(encoded, _dummy_hash(settings))
        return False

    try:
        return bcrypt.checkpw(encoded, hashed.encode("utf-8"))
    except ValueError:
        # A malformed hash in the database. Treat as a failed login rather than
        # a 500, and make it loud in the log.
        logger.error("stored password hash is malformed")
        return False


def needs_rehash(hashed: str, settings: Settings | None = None) -> bool:
    """True when a stored hash uses a weaker cost factor than the current one.

    Lets the cost be raised over time: on a successful login, an old hash can
    be replaced transparently, because the plain password is available at
    exactly that moment and nowhere else.
    """
    settings = settings or get_settings()
    try:
        rounds = int(hashed.split("$")[2])
    except (IndexError, ValueError):
        return True
    return rounds < settings.bcrypt_rounds


def create_token(
    subject: str | int,
    token_type: TokenType,
    role: str,
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Mint a signed JWT.

    A JWT is three base64url segments joined by dots: header, payload,
    signature. The first two are encoded, not encrypted - anyone holding the
    token can read every claim. So a token may carry an id and a role, and must
    never carry anything secret.

    The signature is what makes it trustworthy: without the key, a claim cannot
    be altered without invalidating it.
    """
    settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    if expires_delta is None:
        expires_delta = (
            timedelta(minutes=settings.access_token_expire_minutes)
            if token_type == "access"
            else timedelta(days=settings.refresh_token_expire_days)
        )

    payload: dict[str, Any] = {
        # sub is registered as a string in the JWT spec. Passing an int works
        # with some libraries and is rejected by others, so it is normalised.
        "sub": str(subject),
        "type": token_type,
        "role": role,
        "iat": now,
        "exp": now + expires_delta,
        # A unique id per token, so a future revocation list has something to
        # key on. Not used for revocation here; see Known Gaps.
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


class TokenError(Exception):
    """A token that cannot be trusted, for any reason."""


def decode_token(token: str, expected_type: TokenType, settings: Settings | None = None) -> dict:
    """Verify a token and return its claims.

    algorithms= is a whitelist, and passing it is mandatory rather than
    stylistic. Without it, a decoder that accepts whatever the token's own
    header claims can be handed alg=none and asked to trust an unsigned token.

    The expected_type check is the other half. An access token and a refresh
    token are both validly signed by this service; without checking the claim,
    a long-lived refresh token would be accepted anywhere an access token is,
    which quietly extends every session to the refresh lifetime.
    """
    settings = settings or get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        # Covers a bad signature, malformed structure, and a wrong algorithm.
        # The message given back to the client is deliberately vague.
        raise TokenError("Token is invalid") from exc

    if claims.get("type") != expected_type:
        raise TokenError(f"Expected a {expected_type} token")
    return claims
