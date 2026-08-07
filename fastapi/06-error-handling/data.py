"""In-memory product catalogue, carried over from module 03."""

products: dict[int, dict] = {
    1: {"id": 1, "sku": "HP-2200", "name": "Studio Headphones", "category": "audio", "price": 249.00, "rating": 4.6, "in_stock": True},
    2: {"id": 2, "sku": "EB-1100", "name": "Bluetooth Earbuds", "category": "audio", "price": 79.99, "rating": 4.1, "in_stock": True},
    3: {"id": 3, "sku": "FT-3300", "name": "Fitness Tracker", "category": "wearables", "price": 59.00, "rating": 3.7, "in_stock": True},
    4: {"id": 4, "sku": "KB-4400", "name": "Mechanical Keyboard", "category": "peripherals", "price": 145.00, "rating": 4.7, "in_stock": True},
    5: {"id": 5, "sku": "SS-5500", "name": "Portable SSD 1TB", "category": "storage", "price": 119.00, "rating": 4.5, "in_stock": False},
}


def next_id() -> int:
    """Return the next free product id."""
    return max(products, default=0) + 1


def find_by_sku(sku: str) -> dict | None:
    """Return the product with this SKU, or None."""
    return next((p for p in products.values() if p["sku"] == sku), None)
