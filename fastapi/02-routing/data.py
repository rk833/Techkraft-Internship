"""In-memory data store for the book catalogue.

A module-level dict standing in for a database. It is not thread-safe and it is
lost on restart, which is fine for module 02 - the subject here is routing, and
a real database arrives in module 11.
"""

authors: dict[int, dict] = {
    1: {"id": 1, "name": "Ursula K. Le Guin", "country": "United States"},
    2: {"id": 2, "name": "Chinua Achebe", "country": "Nigeria"},
    3: {"id": 3, "name": "Italo Calvino", "country": "Italy"},
}

books: dict[int, dict] = {
    1: {"id": 1, "title": "A Wizard of Earthsea", "author_id": 1, "year": 1968, "featured": True},
    2: {"id": 2, "title": "The Dispossessed", "author_id": 1, "year": 1974, "featured": False},
    3: {"id": 3, "title": "Things Fall Apart", "author_id": 2, "year": 1958, "featured": True},
    4: {"id": 4, "title": "Invisible Cities", "author_id": 3, "year": 1972, "featured": False},
}


def next_id(store: dict[int, dict]) -> int:
    """Return the next free integer id for a store."""
    return max(store, default=0) + 1
