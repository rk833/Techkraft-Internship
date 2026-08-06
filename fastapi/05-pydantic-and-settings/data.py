"""In-memory order store, plus a stand-in for a database row.

LegacyOrderRow exists to demonstrate from_attributes. It is a plain Python
object with attributes and no dict interface, which is exactly the shape a
SQLAlchemy row has in module 11.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

orders: dict[int, dict] = {}


def next_id() -> int:
    """Return the next free order id."""
    return max(orders, default=0) + 1


@dataclass
class LegacyItemRow:
    """An order line as a plain object rather than a dict."""

    sku: str
    name: str
    unit_price: Decimal
    quantity: int

    @property
    def line_total(self) -> Decimal:
        """Price times quantity."""
        return self.unit_price * self.quantity


@dataclass
class LegacyOrderRow:
    """An order as a plain object, standing in for an ORM row."""

    id: int
    status: str
    created_at: datetime
    customer: dict
    items: list[LegacyItemRow]
    currency: str
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    notes: str | None = None
    tags: list[str] = field(default_factory=list)


def sample_row() -> LegacyOrderRow:
    """Build one LegacyOrderRow to convert in the from_attributes demo."""
    items = [
        LegacyItemRow(sku="KB-4400", name="Mechanical Keyboard", unit_price=Decimal("145.00"), quantity=1),
        LegacyItemRow(sku="MS-1200", name="Wireless Mouse", unit_price=Decimal("42.50"), quantity=2),
    ]
    subtotal = sum((i.line_total for i in items), Decimal("0.00"))
    discount = Decimal("10.00")
    return LegacyOrderRow(
        id=9001,
        status="paid",
        created_at=datetime(2026, 3, 11, 14, 20, tzinfo=timezone.utc),
        customer={
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "address": {
                "line1": "12 Analytical Way",
                "city": "London",
                "postcode": "EC1A 1BB",
                "country": "GB",
            },
        },
        items=items,
        currency="GBP",
        subtotal=subtotal,
        discount=discount,
        total=subtotal - discount,
        notes="Legacy record, loaded from an object rather than a dict.",
        tags=["legacy", "imported"],
    )
