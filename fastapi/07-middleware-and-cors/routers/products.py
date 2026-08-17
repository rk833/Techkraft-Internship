"""Product routes.

Carried over from module 06, plus two routes that exist purely to exercise the
middleware: one slow enough to show a real timing value, one large enough to be
worth compressing.
"""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

import data
from context import get_request_id
from errors import ConflictError, NotFoundError, UpstreamError, ValidationRuleError
from schemas import Category, ERROR_RESPONSES, ProductCreate, ProductRead

logger = logging.getLogger("api.products")

router = APIRouter(prefix="/products", tags=["products"], responses=ERROR_RESPONSES)

ProductId = Annotated[int, Path(ge=1, description="Product id")]


@router.get("", response_model=list[ProductRead], summary="Search products")
def search_products(
    category: Annotated[Category | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict]:
    """Search the catalogue."""
    # Reads the id set by middleware. No parameter was threaded through to get
    # it here, which is the point of using a ContextVar.
    logger.info("search category=%s limit=%s", category, limit)
    results = list(data.products.values())
    if category is not None:
        results = [p for p in results if p["category"] == category.value]
    return results[:limit]


@router.get("/slow", summary="A deliberately slow endpoint")
def slow(ms: Annotated[int, Query(ge=0, le=2000)] = 250) -> dict:
    """Sleep for a while so the timing header shows something real."""
    time.sleep(ms / 1000)
    return {"slept_ms": ms, "request_id": get_request_id()}


@router.get("/bulk", summary="A large, compressible response")
def bulk(count: Annotated[int, Query(ge=1, le=5000)] = 800) -> dict:
    """Return a repetitive payload.

    Highly repetitive JSON compresses extremely well, which makes the effect of
    GZipMiddleware obvious rather than marginal.
    """
    return {
        "items": [
            {
                "id": i,
                "name": "Repetitive Product Name For Compression Demonstration",
                "category": "peripherals",
                "description": "The same sentence over and over compresses very well indeed.",
            }
            for i in range(count)
        ]
    }


@router.get("/boom", summary="Trigger an unhandled exception")
def boom() -> dict:
    """Raise an error nobody anticipated."""
    denominator = 0
    return {"result": 42 / denominator}


@router.get("/upstream", summary="Simulate a failing dependency")
def upstream_call() -> dict:
    """Fail as though a dependency were down."""
    raise UpstreamError("The pricing service did not respond within 2000ms")


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
        raise ConflictError(f"SKU {payload.sku} already exists")
    product = {**payload.model_dump(), "id": data.next_id()}
    data.products[product["id"]] = product
    return product
