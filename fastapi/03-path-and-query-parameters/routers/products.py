"""Product routes.

The search endpoint is the point of this module. Every filter arrives as a
query parameter, and every constraint on those parameters is declared in the
signature rather than checked in the body.
"""

from enum import Enum
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status

import data
from data import Category

router = APIRouter(prefix="/products", tags=["products"])


class SortBy(str, Enum):
    """Fields the result set can be sorted by."""

    NAME = "name"
    PRICE = "price"
    RATING = "rating"


class SortOrder(str, Enum):
    """Sort direction."""

    ASC = "asc"
    DESC = "desc"


# Static segment before the dynamic /{product_id}, same rule as module 02.
@router.get("/categories", summary="List available categories")
def list_categories() -> list[str]:
    """Return the category values the search endpoint will accept."""
    return [c.value for c in Category]


@router.get("", summary="Search products")
def search_products(
    # Annotated[type, Query(...)] is the current way to attach metadata to a
    # parameter. The older style, `q: str | None = Query(None, ...)`, still
    # works but puts the default in two places and reads worse.
    q: Annotated[
        str | None,
        Query(min_length=2, max_length=50, description="Free text match on the product name"),
    ] = None,
    category: Annotated[
        Category | None,
        Query(description="Restrict to one category"),
    ] = None,
    min_price: Annotated[float | None, Query(ge=0, description="Inclusive lower bound")] = None,
    max_price: Annotated[float | None, Query(ge=0, description="Inclusive upper bound")] = None,
    min_rating: Annotated[float | None, Query(ge=0, le=5, description="Inclusive, 0 to 5")] = None,
    in_stock: Annotated[bool | None, Query(description="Filter by availability")] = None,
    # A list parameter is repeated in the query string: ?tags=wired&tags=premium
    tags: Annotated[
        list[str] | None,
        Query(description="Repeat the parameter for each tag. All must match."),
    ] = None,
    sort_by: Annotated[SortBy, Query(description="Field to sort on")] = SortBy.NAME,
    order: Annotated[SortOrder, Query(description="Sort direction")] = SortOrder.ASC,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 20,
    offset: Annotated[int, Query(ge=0, description="Rows to skip")] = 0,
) -> dict:
    """Search the catalogue.

    Every parameter is optional, so a bare GET returns the first page of
    everything. Nothing in this function body validates types or ranges -
    FastAPI has already rejected anything invalid with a 422 before the first
    line runs.
    """
    # One thing FastAPI cannot check from the signature: a rule spanning two
    # parameters. Cross-field validation needs a model, which is module 05.
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            # HTTP_422_UNPROCESSABLE_ENTITY is deprecated in this Starlette
            # version and emits a warning. Same code, renamed constant.
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"min_price ({min_price}) cannot exceed max_price ({max_price})",
        )

    results = data.products

    if q is not None:
        needle = q.casefold()
        results = [p for p in results if needle in p["name"].casefold()]
    if category is not None:
        results = [p for p in results if p["category"] == category.value]
    if min_price is not None:
        results = [p for p in results if p["price"] >= min_price]
    if max_price is not None:
        results = [p for p in results if p["price"] <= max_price]
    if min_rating is not None:
        results = [p for p in results if p["rating"] >= min_rating]
    if in_stock is not None:
        results = [p for p in results if p["in_stock"] is in_stock]
    if tags:
        wanted = set(tags)
        results = [p for p in results if wanted.issubset(p["tags"])]

    results = sorted(results, key=lambda p: p[sort_by.value], reverse=order is SortOrder.DESC)

    # total is the count before paging, so the client can work out how many
    # pages exist. Returning only len(page) would make that impossible.
    total = len(results)
    page = results[offset : offset + limit]

    return {
        "total": total,
        "count": len(page),
        "limit": limit,
        "offset": offset,
        "items": page,
    }


@router.get("/{product_id}", summary="Get one product")
def get_product(
    # Path() takes the same constraints as Query(). ge=1 means a request for
    # /products/0 or /products/-3 is rejected as 422 before this runs, so the
    # only failure left to handle is a valid id that does not exist.
    product_id: Annotated[int, Path(ge=1, description="Product id, 1 or greater")],
) -> dict:
    """Return a single product by id."""
    for product in data.products:
        if product["id"] == product_id:
            return product
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"No product with id {product_id}")
