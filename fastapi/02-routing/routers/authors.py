"""Author routes.

A second router, to show that adding a resource means adding a file rather than
growing main.py. Includes a nested route, /authors/{id}/books, which is the
conventional way to express "the books belonging to this author".
"""

from fastapi import APIRouter, HTTPException, status

import data

router = APIRouter(prefix="/authors", tags=["authors"])


@router.get("", summary="List all authors")
def list_authors() -> list[dict]:
    """Return every author."""
    return list(data.authors.values())


@router.get("/{author_id}", summary="Get one author")
def get_author(author_id: int) -> dict:
    """Return a single author by id."""
    author = data.authors.get(author_id)
    if author is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No author with id {author_id}")
    return author


@router.get("/{author_id}/books", summary="List an author's books")
def list_author_books(author_id: int) -> list[dict]:
    """Return the books written by one author.

    The 404 is raised for an unknown author rather than returning an empty
    list, because "this author does not exist" and "this author has written
    nothing" are different answers and the client needs to tell them apart.
    """
    if author_id not in data.authors:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No author with id {author_id}")
    return [book for book in data.books.values() if book["author_id"] == author_id]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Add an author")
def create_author(payload: dict) -> dict:
    """Add an author. Unvalidated for now - see the note in books.py."""
    author = {
        "id": data.next_id(data.authors),
        "name": payload.get("name"),
        "country": payload.get("country"),
    }
    data.authors[author["id"]] = author
    return author
