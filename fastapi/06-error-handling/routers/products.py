"""Product routes.

Handlers raise domain exceptions and never build an error response. They do not
import JSONResponse, do not know what the envelope looks like, and do not know
which status code their exception carries. That knowledge lives in errors.py
and handlers.py, in one place.
"""

import random
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

import data
from errors import ConflictError, NotFoundError, UpstreamError, ValidationRuleError
from schemas import Category, ERROR_RESPONSES, ProductCreate, ProductRead

router = APIRouter(prefix="/products", tags=["products"], responses=ERROR_RESPONSES)

ProductId = Annotated[int, Path(ge=1, description="Product id")]


@router.get("", response_model=list[ProductRead], summary="Search products")
def search_products(
    category: Annotated[Category | None, Query()] = None,
    min_price: Annotated[float | None, Query(ge=0)] = None,
    max_price: Annotated[float | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict]:
    """Search the catalogue.

    The cross-field rule that module 03 raised as a bare HTTPException with a
    plain string body is now a ValidationRuleError. It arrives at the client in
    the same envelope, with the same code, as FastAPI's own 422s.
    """
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ValidationRuleError(
            "min_price cannot exceed max_price",
            details=[
                {"field": "query.min_price", "message": f"{min_price} exceeds max_price", "type": "range_inverted"},
                {"field": "query.max_price", "message": f"{max_price} is below min_price", "type": "range_inverted"},
            ],
        )

    results = list(data.products.values())
    if category is not None:
        results = [p for p in results if p["category"] == category.value]
    if min_price is not None:
        results = [p for p in results if p["price"] >= min_price]
    if max_price is not None:
        results = [p for p in results if p["price"] <= max_price]
    return results[:limit]


@router.get("/boom", summary="Trigger an unhandled exception")
def boom() -> dict:
    """Raise an error nobody anticipated.

    Deliberately a bug: a ZeroDivisionError with no try/except anywhere near
    it. This is what the catch-all handler exists for, and the only honest way
    to demonstrate that a genuinely unexpected failure still produces the
    envelope and still hides its traceback.
    """
    denominator = 0
    return {"result": 42 / denominator}


@router.get("/upstream", summary="Simulate a failing dependency")
def upstream_call() -> dict:
    """Call a dependency that is not answering.

    Raised as 503 rather than 500 because the fault is elsewhere and retrying
    is reasonable. Getting this distinction right is what lets a client behave
    sensibly instead of giving up.
    """
    raise UpstreamError(
        "The pricing service did not respond within 2000ms",
        details=[{"field": None, "message": "pricing-service timeout", "type": "timeout"}],
    )


@router.get("/flaky", summary="Fail unpredictably")
def flaky() -> dict:
    """Fail roughly half the time, in a way nothing anticipated.

    Present so the log output can be inspected across repeated calls without
    restarting anything.
    """
    if random.random() < 0.5:
        raise RuntimeError("downstream cache returned a corrupt entry")
    return {"result": "ok"}


@router.get("/{product_id}", response_model=ProductRead, summary="Get one product")
def get_product(product_id: ProductId) -> dict:
    """Return a single product."""
    product = data.products.get(product_id)
    if product is None:
        raise NotFoundError(f"No product with id {product_id}")
    return product


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED, summary="Add a product")
def create_product(payload: ProductCreate) -> dict:
    """Add a product to the catalogue."""
    if data.find_by_sku(payload.sku):
        raise ConflictError(
            f"SKU {payload.sku} already exists",
            details=[{"field": "body.sku", "message": "must be unique", "type": "duplicate"}],
        )
    product = {**payload.model_dump(), "id": data.next_id()}
    data.products[product["id"]] = product
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a product")
def delete_product(product_id: ProductId) -> None:
    """Delete a product."""
    if product_id not in data.products:
        raise NotFoundError(f"No product with id {product_id}")
    del data.products[product_id]
