"""Schemas, including the error envelope carried over from module 06."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from errors import ErrorCode


class ErrorDetail(BaseModel):
    """One specific thing that was wrong."""

    field: str | None = None
    message: str
    type: str | None = None


class ErrorBody(BaseModel):
    """The contents of the error envelope."""

    code: ErrorCode
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
    # In module 06 this was generated inside the error handlers, so only failing
    # requests had one. It is now the request id assigned by middleware, which
    # means a client can quote it for a successful request too.
    reference: str


class ErrorResponse(BaseModel):
    """Every failure from this API looks like this."""

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


ERROR_RESPONSES: dict[int | str, dict] = {
    404: {"model": ErrorResponse, "description": "Not found"},
    409: {"model": ErrorResponse, "description": "Conflict with existing state"},
    422: {"model": ErrorResponse, "description": "Validation failed"},
    500: {"model": ErrorResponse, "description": "Unhandled server error"},
    503: {"model": ErrorResponse, "description": "Upstream dependency unavailable"},
}
