"""Order schemas.

This is the file the module is about. It covers nested models, field and model
validators, aliases, computed fields, strict extra handling, and from_attributes.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

# A reusable annotated type. Declaring the money rules once means every price
# in the API agrees on them, and a change lands everywhere at once.
Money = Annotated[Decimal, Field(max_digits=10, decimal_places=2, ge=0)]


class Currency(str, Enum):
    """Supported settlement currencies."""

    GBP = "GBP"
    EUR = "EUR"
    USD = "USD"
    NPR = "NPR"


class OrderStatus(str, Enum):
    """Lifecycle states an order can be in."""

    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"


class StrictModel(BaseModel):
    """Base for every request schema.

    extra="forbid" closes the gap left open in module 04, where a body
    containing "is_admin": true was accepted and silently discarded. Rejecting
    unknown keys turns a client typo into a 422 instead of a field that quietly
    does nothing.

    populate_by_name lets a field be supplied by either its Python name or its
    alias, so adding an alias for a JavaScript client does not break existing
    callers.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Address(StrictModel):
    """A postal address. Nested inside Customer."""

    line1: str = Field(min_length=3, max_length=100)
    line2: str | None = Field(default=None, max_length=100)
    city: str = Field(min_length=2, max_length=60)
    postcode: str = Field(min_length=3, max_length=12)
    # ISO 3166-1 alpha-2. The pattern is enforced by pydantic, not by us.
    country: str = Field(pattern=r"^[A-Za-z]{2}$", description="Two letter country code")

    @field_validator("country")
    @classmethod
    def uppercase_country(cls, value: str) -> str:
        """Normalise the country code to uppercase.

        mode="after" is the default: this runs once the value has already been
        confirmed to be a string matching the pattern. So it never has to
        defend against being handed an int.
        """
        return value.upper()


class Customer(StrictModel):
    """Who the order is for. One level of nesting; Address makes it two."""

    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    address: Address


class OrderItemCreate(StrictModel):
    """One line on an incoming order."""

    sku: str = Field(min_length=4, max_length=20, pattern=r"^[A-Za-z0-9-]+$")
    name: str = Field(min_length=2, max_length=80)
    # An explicit alias. A JavaScript client can send unitPrice; a Python one
    # can still send unit_price, because populate_by_name is on.
    unit_price: Money = Field(alias="unitPrice")
    quantity: int = Field(ge=1, le=999)

    @field_validator("sku")
    @classmethod
    def normalise_sku(cls, value: str) -> str:
        """Uppercase the SKU so lookups are not case dependent."""
        return value.upper()

    @computed_field
    @property
    def line_total(self) -> Decimal:
        """Price times quantity.

        A computed field is derived, so it appears in output but is not
        accepted as input. A client cannot send a line_total that disagrees
        with the price and quantity, because there is nowhere to put it.
        """
        return self.unit_price * self.quantity


class OrderCreate(StrictModel):
    """An incoming order."""

    customer: Customer
    items: list[OrderItemCreate] = Field(min_length=1, max_length=20)
    currency: Currency = Currency.GBP
    discount: Money = Decimal("0.00")
    notes: str | None = Field(default=None, max_length=300)
    # default_factory rather than "= []". In pydantic a bare [] is actually
    # safe, because pydantic deep-copies defaults per instance - the classic
    # shared-mutable-default bug does not apply here. default_factory is still
    # the better habit: it is required for plain dataclasses and for any
    # default that has to be computed per instance.
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("tags", mode="before")
    @classmethod
    def allow_single_tag(cls, value: Any) -> Any:
        """Accept a bare string where a list of tags is expected.

        mode="before" runs against the raw input, ahead of type coercion, which
        is the only place this can work - by the time the default validator has
        run, a string would already have been rejected as not-a-list.
        """
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("notes")
    @classmethod
    def blank_notes_are_none(cls, value: str | None) -> str | None:
        """Treat a whitespace-only note as no note at all."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("items")
    @classmethod
    def reject_duplicate_skus(cls, items: list[OrderItemCreate]) -> list[OrderItemCreate]:
        """Refuse an order listing the same SKU twice.

        A field validator can see the whole list, so a rule about the
        relationship between elements still belongs here rather than in a model
        validator. A model validator is only needed for rules spanning
        different fields.
        """
        seen = [item.sku for item in items]
        duplicates = {s for s in seen if seen.count(s) > 1}
        if duplicates:
            raise ValueError(f"duplicate SKUs: {', '.join(sorted(duplicates))}")
        return items

    @computed_field
    @property
    def subtotal(self) -> Decimal:
        """Sum of every line total, before discount."""
        return sum((item.line_total for item in self.items), Decimal("0.00"))

    @model_validator(mode="after")
    def discount_within_subtotal(self) -> "OrderCreate":
        """Reject a discount larger than the order itself.

        This is the rule module 03 had to write by hand in the endpoint, because
        FastAPI validates parameters one at a time and cannot see across them.
        Here it is part of the schema, so it applies everywhere the model is
        used and appears in the same 422 as every other validation error.

        mode="after" means every individual field has already validated, so
        self.discount and self.items are both known to be the right types.
        """
        if self.discount > self.subtotal:
            raise ValueError(
                f"discount {self.discount} exceeds subtotal {self.subtotal}"
            )
        return self


class OrderItemRead(BaseModel):
    """One line on a stored order."""

    # from_attributes lets model_validate read a plain object's attributes
    # rather than requiring a dict. Module 11 depends on this to turn
    # SQLAlchemy rows into response models.
    model_config = ConfigDict(from_attributes=True)

    sku: str
    name: str
    unit_price: Money
    quantity: int
    line_total: Money


class OrderRead(BaseModel):
    """A stored order, as returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: OrderStatus
    created_at: datetime
    customer: Customer
    items: list[OrderItemRead]
    currency: Currency
    subtotal: Money
    discount: Money
    total: Money
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class SettingsRead(BaseModel):
    """The configuration the service is running with."""

    app_name: str
    environment: str
    debug: bool
    log_level: str
    max_items_per_order: int
    is_production: bool
    env_file: str
