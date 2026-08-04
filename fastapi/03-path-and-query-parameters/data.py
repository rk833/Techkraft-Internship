"""In-memory product catalogue.

Enough rows, and enough spread across category, price, rating and stock, that
every filter in the search endpoint can be shown to actually do something.
"""

from enum import Enum


class Category(str, Enum):
    """Allowed product categories.

    Inheriting from str as well as Enum matters: it makes the members behave as
    strings when serialised to JSON, and lets FastAPI accept the plain string
    "audio" from a query string rather than requiring the Python member.
    """

    AUDIO = "audio"
    WEARABLES = "wearables"
    PERIPHERALS = "peripherals"
    STORAGE = "storage"


products: list[dict] = [
    {"id": 1, "name": "Studio Headphones", "category": "audio", "price": 249.00, "rating": 4.6, "in_stock": True, "tags": ["wired", "over-ear"]},
    {"id": 2, "name": "Bluetooth Earbuds", "category": "audio", "price": 79.99, "rating": 4.1, "in_stock": True, "tags": ["wireless", "in-ear"]},
    {"id": 3, "name": "Desk Speaker Pair", "category": "audio", "price": 189.50, "rating": 3.9, "in_stock": False, "tags": ["wired"]},
    {"id": 4, "name": "Fitness Tracker", "category": "wearables", "price": 59.00, "rating": 3.7, "in_stock": True, "tags": ["wireless", "waterproof"]},
    {"id": 5, "name": "Smart Watch", "category": "wearables", "price": 329.00, "rating": 4.8, "in_stock": True, "tags": ["wireless", "waterproof", "premium"]},
    {"id": 6, "name": "Mechanical Keyboard", "category": "peripherals", "price": 145.00, "rating": 4.7, "in_stock": True, "tags": ["wired", "premium"]},
    {"id": 7, "name": "Wireless Mouse", "category": "peripherals", "price": 42.50, "rating": 4.0, "in_stock": True, "tags": ["wireless"]},
    {"id": 8, "name": "Ergonomic Trackball", "category": "peripherals", "price": 88.00, "rating": 3.4, "in_stock": False, "tags": ["wired"]},
    {"id": 9, "name": "Portable SSD 1TB", "category": "storage", "price": 119.00, "rating": 4.5, "in_stock": True, "tags": ["usb-c", "portable"]},
    {"id": 10, "name": "NAS Drive 4TB", "category": "storage", "price": 210.00, "rating": 4.2, "in_stock": False, "tags": ["network"]},
    {"id": 11, "name": "SD Card 256GB", "category": "storage", "price": 34.99, "rating": 3.8, "in_stock": True, "tags": ["portable"]},
    {"id": 12, "name": "Studio Microphone", "category": "audio", "price": 165.00, "rating": 4.4, "in_stock": True, "tags": ["wired", "usb-c", "premium"]},
]
