"""REST Order Service (port 8080). Calls the REST Inventory Service over HTTP/JSON.

POST /orders  {"item_id": "apple", "quantity": 2}
  201 -> order confirmed
  400 -> malformed request
  404 / 409 -> rejected by inventory (unknown item / insufficient stock)
  503 -> inventory unreachable
  504 -> inventory did not answer within INVENTORY_TIMEOUT_SECONDS
"""

import logging
import os
import time
import uuid

import requests
from flask import Flask, jsonify, request

# 127.0.0.1 rather than localhost: on Windows "localhost" tries IPv6 first and
# Flask only listens on IPv4, which adds ~2s to every call.
INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://127.0.0.1:8081")
TIMEOUT_SECONDS = float(os.environ.get("INVENTORY_TIMEOUT_SECONDS", "2.0"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [order-rest] %(message)s")
log = logging.getLogger(__name__)
app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify(status="ok", service="order-rest")


@app.post("/orders")
def create_order():
    body = request.get_json(silent=True) or {}
    item_id = body.get("item_id")
    quantity = body.get("quantity")
    if not isinstance(item_id, str) or not isinstance(quantity, int) or quantity <= 0:
        return jsonify(error="item_id (string) and quantity (positive integer) are required"), 400

    start = time.perf_counter()
    try:
        resp = requests.post(f"{INVENTORY_URL}/inventory/check",
                             json={"item_id": item_id, "quantity": quantity},
                             timeout=TIMEOUT_SECONDS)
    except requests.Timeout:
        log.error("inventory timed out after %.1fs (item=%s)", TIMEOUT_SECONDS, item_id)
        return jsonify(status="FAILED",
                       error=f"inventory service timed out after {TIMEOUT_SECONDS}s"), 504
    except requests.ConnectionError:
        log.error("inventory unreachable at %s (item=%s)", INVENTORY_URL, item_id)
        return jsonify(status="FAILED", error="inventory service unavailable"), 503
    latency_ms = (time.perf_counter() - start) * 1000

    try:
        inventory = resp.json()
    except ValueError:
        log.error("inventory returned non-JSON response (status %d)", resp.status_code)
        return jsonify(status="FAILED", error="bad response from inventory service"), 502

    if resp.status_code == 200:
        order_id = str(uuid.uuid4())[:8]
        log.info("order %s confirmed item=%s qty=%d (inventory %.0fms)", order_id, item_id, quantity, latency_ms)
        return jsonify(order_id=order_id, status="CONFIRMED", item_id=item_id,
                       quantity=quantity, inventory=inventory), 201

    log.info("order rejected item=%s qty=%d -> %d (inventory %.0fms)", item_id, quantity, resp.status_code, latency_ms)
    return jsonify(status="REJECTED", item_id=item_id, quantity=quantity,
                   reason=inventory.get("error"), inventory=inventory), resp.status_code


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", "8080")))
