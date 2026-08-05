"""In-memory user store.

Each stored record deliberately holds more than UserRead exposes: a password
and an internal_note. That surplus is what proves the response model is doing
the filtering, rather than the store simply never having had the field.
"""

from datetime import datetime, timezone

users: dict[int, dict] = {
    1: {
        "id": 1,
        "username": "rkhadka",
        "email": "rkhadka@example.com",
        "full_name": "Ridesha Khadka",
        "bio": "Learning FastAPI.",
        "is_active": True,
        "created_at": datetime(2026, 1, 14, 9, 30, tzinfo=timezone.utc),
        # Plain text, and wrong. Module 12 replaces this with a bcrypt hash.
        # Kept visible here so the response model has something real to hide.
        "password": "correct-horse-battery",
        "internal_note": "seed account, do not expose",
    },
    2: {
        "id": 2,
        "username": "acalvino",
        "email": "acalvino@example.com",
        "full_name": None,
        "bio": None,
        "is_active": False,
        "created_at": datetime(2026, 2, 2, 16, 5, tzinfo=timezone.utc),
        "password": "invisible-cities",
        "internal_note": "deactivated on request",
    },
}


def next_id() -> int:
    """Return the next free user id."""
    return max(users, default=0) + 1


def find_by_username(username: str) -> dict | None:
    """Return the user with this username, or None."""
    return next((u for u in users.values() if u["username"] == username), None)


def find_by_email(email: str) -> dict | None:
    """Return the user with this email, or None."""
    return next((u for u in users.values() if u["email"] == email), None)
