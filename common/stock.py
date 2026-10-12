"""Shared in-memory stock table and lookup logic used by both Inventory Services.

Keeping this in one place guarantees the REST and gRPC versions implement the
exact same business rules; only the transport differs.
"""

import os
import time

STOCK = {
    "apple": 10,
    "banana": 5,
    "laptop": 2,
}


class UnknownItem(Exception):
    pass


class InsufficientStock(Exception):
    def __init__(self, available):
        super().__init__(f"only {available} in stock")
        self.available = available


def simulated_delay():
    """Sleep for INVENTORY_DELAY_SECONDS (default 0) to simulate a slow service."""
    delay = float(os.environ.get("INVENTORY_DELAY_SECONDS", "0"))
    if delay > 0:
        time.sleep(delay)
    return delay


def check(item_id, quantity):
    """Return the available quantity, or raise UnknownItem / InsufficientStock."""
    if item_id not in STOCK:
        raise UnknownItem(item_id)
    available = STOCK[item_id]
    if quantity > available:
        raise InsufficientStock(available)
    return available
