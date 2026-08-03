"""Book routes.

Every HTTP method the catalogue needs, on one resource. The prefix and tag are
declared once on the router rather than repeated on each decorator.
"""

from fastapi import APIRouter, HTTPException, status

import data

router = APIRouter(prefix="/books", tags=["books"])


@router.get("", summary="List all books")
def list_books() -> list[dict]:
    """Return every book in the catalogue."""
    return list(data.books.values())


# Route order matters. This must be declared before /{book_id}, because FastAPI
# matches routes top to bottom and stops at the first hit. If /{book_id} came
# first it would match the literal path /books/featured, try to coerce
# "featured" to an int, fail, and return 422 - a route that is unreachable
# rather than broken, which is far harder to debug.
@router.get("/featured", summary="List featured books")
def list_featured_books() -> list[dict]:
    """Return only the books flagged as featured."""
    return [book for book in data.books.values() if book["featured"]]


@router.get("/{book_id}", summary="Get one book")
def get_book(book_id: int) -> dict:
    """Return a single book by id."""
    book = data.books.get(book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No book with id {book_id}")
    return book


@router.post("", status_code=status.HTTP_201_CREATED, summary="Add a book")
def create_book(payload: dict) -> dict:
    """Add a book to the catalogue.

    The payload is an untyped dict, so nothing here is validated - any JSON
    object is accepted and stored. This is deliberate. Module 04 replaces it
    with a Pydantic model, and the difference is easier to appreciate after
    seeing what the absence of one costs.
    """
    book = {
        "id": data.next_id(data.books),
        "title": payload.get("title"),
        "author_id": payload.get("author_id"),
        "year": payload.get("year"),
        "featured": payload.get("featured", False),
    }
    data.books[book["id"]] = book
    return book


@router.put("/{book_id}", summary="Replace a book")
def replace_book(book_id: int, payload: dict) -> dict:
    """Replace a book entirely.

    PUT is a full replacement: any field the client omits is reset, not kept.
    It is idempotent - sending the same request twice leaves the same state.
    """
    if book_id not in data.books:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No book with id {book_id}")
    book = {
        "id": book_id,
        "title": payload.get("title"),
        "author_id": payload.get("author_id"),
        "year": payload.get("year"),
        "featured": payload.get("featured", False),
    }
    data.books[book_id] = book
    return book


@router.patch("/{book_id}", summary="Update part of a book")
def update_book(book_id: int, payload: dict) -> dict:
    """Update only the fields the client sent, leaving the rest alone."""
    book = data.books.get(book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No book with id {book_id}")
    # id is not client-writable, so it is dropped from any incoming payload
    book.update({k: v for k, v in payload.items() if k != "id"})
    return book


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a book")
def delete_book(book_id: int) -> None:
    """Remove a book from the catalogue.

    204 means success with no body, so this returns None. Returning a value
    alongside a 204 would be a protocol violation.
    """
    if book_id not in data.books:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No book with id {book_id}")
    del data.books[book_id]
