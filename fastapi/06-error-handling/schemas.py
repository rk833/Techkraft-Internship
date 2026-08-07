"""Request and response schemas, including the single error envelope.

The error models exist so that the failure shape is documented in OpenAPI
rather than being an undocumented convention. A client generated from the
schema gets a type for the error case, not just for the happy path.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from errors import ErrorCode


class ErrorDetail(BaseModel):
    """One specific thing that was wrong, when more than one thing can be."""

    field: str | None = Field(default=None, description="Dotted path to the offending input")
    message: str = Field(description="What was wrong with it")
    type: str | None = Field(default=None, description="Machine-readable failure type")


class ErrorBody(BaseModel):
    """The contents of the error envelope."""

    code: ErrorCode = Field(description="Stable machine-readable code, safe to branch on")
    message: str = Field(description="Human-readable summary, not safe to branch on")
    details: list[ErrorDetail] = Field(
        default_factory=list,
        description="Per-field failures, empty when the error is not field specific",
    )
    reference: str = Field(description="Correlates this response with the server log entry")


class ErrorResponse(BaseModel):
    """Every failure from this API, at every status code, looks like this."""

    error: ErrorBody


class Category(str, Enum):
    """Allowed product categories."""

    AUDIO = "audio"
    WEARABLES = "wearables"
    PERIPHERALS = "peripherals"
    STORAGE = "storage"


class ProductCreate(BaseModel):
    """A new product."""

    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=4, max_length=20, pattern=r"^[A-Za-z0-9-]+$")
    name: str = Field(min_length=2, max_length=80)
    category: Category
    price: float = Field(gt=0, le=100_000)
    rating: float = Field(default=0.0, ge=0, le=5)
    in_stock: bool = True


class ProductRead(BaseModel):
    """A product as returned to the client."""

    id: int
    sku: str
    name: str
    category: Category
    price: float
    rating: float
    in_stock: bool


# Attached to routers so the error shape appears in the generated docs for
# every route rather than only where someone remembered to declare it.
ERROR_RESPONSES: dict[int | str, dict] = {
    404: {"model": ErrorResponse, "description": "Not found"},
    409: {"model": ErrorResponse, "description": "Conflict with existing state"},
    422: {"model": ErrorResponse, "description": "Validation failed"},
    500: {"model": ErrorResponse, "description": "Unhandled server error"},
    503: {"model": ErrorResponse, "description": "Upstream dependency unavailable"},
}
