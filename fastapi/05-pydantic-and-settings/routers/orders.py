"""Order routes.

The handlers are short on purpose. Nearly every rule that would otherwise sit
here as an if-statement lives in schemas.py instead, which means it is enforced
consistently and documented automatically.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status

import data
from config import get_settings
from schemas import OrderCreate, OrderRead, OrderStatus

router = APIRouter(prefix="/orders", tags=["orders"])

OrderId = Annotated[int, Path(ge=1, description="Order id")]


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED, summary="Place an order")
def create_order(payload: OrderCreate) -> dict:
    """Create an order.

    Note what is not here: no length check on items, no price check, no
    discount-versus-subtotal comparison, no SKU deduplication. All of it ran
    before this function was entered.
    """
    settings = get_settings()
    # A limit that comes from configuration rather than from the schema, because
    # it is an operational choice rather than a property of an order.
    if len(payload.items) > settings.max_items_per_order:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"An order may contain at most {settings.max_items_per_order} items",
        )

    order = {
        "id": data.next_id(),
        "status": OrderStatus.PENDING,
        "created_at": datetime.now(timezone.utc),
        "customer": payload.customer.model_dump(),
        "items": [item.model_dump() for item in payload.items],
        "currency": payload.currency,
        "subtotal": payload.subtotal,
        "discount": payload.discount,
        "total": payload.subtotal - payload.discount,
        "notes": payload.notes,
        "tags": payload.tags,
    }
    data.orders[order["id"]] = order
    return order


@router.get("", response_model=list[OrderRead], summary="List orders")
def list_orders() -> list[dict]:
    """Return every order placed since the process started."""
    return list(data.orders.values())


@router.get("/legacy-demo", response_model=OrderRead, summary="from_attributes demo")
def legacy_demo() -> data.LegacyOrderRow:
    """Return an order built from a plain object rather than a dict.

    OrderRead sets from_attributes=True, so FastAPI can read this object's
    attributes directly. Without it the conversion fails, because the object
    has no dict interface. This is the mechanism module 11 relies on to turn
    SQLAlchemy rows into responses.
    """
    return data.sample_row()


@router.get("/{order_id}", response_model=OrderRead, summary="Get one order")
def get_order(order_id: OrderId) -> dict:
    """Return a single order."""
    order = data.orders.get(order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No order with id {order_id}")
    return order
