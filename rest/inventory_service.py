"""REST Inventory Service (port 8081).

POST /inventory/check  {"item_id": "apple", "quantity": 2}
  200 -> item available
  400 -> malformed request
  404 -> unknown item
  409 -> not enough stock
"""

import logging
import os

from flask import Flask, jsonify, request

from common import stock

logging.basicConfig(level=logging.INFO, format="%(asctime)s [inventory-rest] %(message)s")
log = logging.getLogger(__name__)
app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify(status="ok", service="inventory-rest")


@app.post("/inventory/check")
def check_inventory():
    body = request.get_json(silent=True) or {}
    item_id = body.get("item_id")
    quantity = body.get("quantity")
    if not isinstance(item_id, str) or not isinstance(quantity, int) or quantity <= 0:
        return jsonify(error="item_id (string) and quantity (positive integer) are required"), 400

    delay = stock.simulated_delay()
    if delay:
        log.info("simulated delay of %.1fs applied", delay)

    try:
        available = stock.check(item_id, quantity)
    except stock.UnknownItem:
        log.info("check item=%s qty=%d -> 404 unknown item", item_id, quantity)
        return jsonify(item_id=item_id, available=False, error="unknown item"), 404
    except stock.InsufficientStock as e:
        log.info("check item=%s qty=%d -> 409 insufficient (have %d)", item_id, quantity, e.available)
        return jsonify(item_id=item_id, requested_quantity=quantity,
                       available_quantity=e.available, available=False,
                       error="insufficient stock"), 409

    log.info("check item=%s qty=%d -> 200 available (have %d)", item_id, quantity, available)
    return jsonify(item_id=item_id, requested_quantity=quantity,
                   available_quantity=available, available=True), 200


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", "8081")))
