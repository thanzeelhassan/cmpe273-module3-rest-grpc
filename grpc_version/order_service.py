"""gRPC Order Service (port 8082).

Exposes the same POST /orders HTTP API as the REST Order Service, but talks to
the Inventory Service over gRPC with a deadline.

  201 -> order confirmed
  400 -> malformed request
  404 -> NOT_FOUND from inventory
  409 -> FAILED_PRECONDITION from inventory
  503 -> UNAVAILABLE (inventory unreachable)
  504 -> DEADLINE_EXCEEDED (inventory slower than INVENTORY_DEADLINE_SECONDS)
"""

import logging
import os
import time
import uuid

import grpc
from flask import Flask, jsonify, request

from proto import inventory_pb2, inventory_pb2_grpc

INVENTORY_ADDR = os.environ.get("INVENTORY_ADDR", "127.0.0.1:50051")
DEADLINE_SECONDS = float(os.environ.get("INVENTORY_DEADLINE_SECONDS", "2.0"))

GRPC_TO_HTTP = {
    grpc.StatusCode.INVALID_ARGUMENT: 400,
    grpc.StatusCode.NOT_FOUND: 404,
    grpc.StatusCode.FAILED_PRECONDITION: 409,
    grpc.StatusCode.UNAVAILABLE: 503,
    grpc.StatusCode.DEADLINE_EXCEEDED: 504,
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [order-grpc] %(message)s")
log = logging.getLogger(__name__)
app = Flask(__name__)

# One long-lived channel; gRPC reuses the HTTP/2 connection across calls.
channel = grpc.insecure_channel(INVENTORY_ADDR)
inventory = inventory_pb2_grpc.InventoryServiceStub(channel)


@app.get("/health")
def health():
    return jsonify(status="ok", service="order-grpc")


@app.post("/orders")
def create_order():
    body = request.get_json(silent=True) or {}
    item_id = body.get("item_id")
    quantity = body.get("quantity")
    if not isinstance(item_id, str) or not isinstance(quantity, int) or quantity <= 0:
        return jsonify(error="item_id (string) and quantity (positive integer) are required"), 400

    start = time.perf_counter()
    try:
        reply = inventory.CheckInventory(
            inventory_pb2.CheckInventoryRequest(item_id=item_id, quantity=quantity),
            timeout=DEADLINE_SECONDS)
    except grpc.RpcError as e:
        code = e.code()
        http_status = GRPC_TO_HTTP.get(code, 502)
        if code in (grpc.StatusCode.DEADLINE_EXCEEDED, grpc.StatusCode.UNAVAILABLE):
            log.error("inventory call failed: %s after %.1fs deadline (item=%s)", code.name, DEADLINE_SECONDS, item_id)
            return jsonify(status="FAILED", grpc_status=code.name, error=e.details()), http_status
        log.info("order rejected item=%s qty=%d -> %s", item_id, quantity, code.name)
        return jsonify(status="REJECTED", item_id=item_id, quantity=quantity,
                       grpc_status=code.name, reason=e.details()), http_status
    latency_ms = (time.perf_counter() - start) * 1000

    order_id = str(uuid.uuid4())[:8]
    log.info("order %s confirmed item=%s qty=%d (inventory %.0fms)", order_id, item_id, quantity, latency_ms)
    return jsonify(order_id=order_id, status="CONFIRMED", item_id=item_id, quantity=quantity,
                   inventory={"available": reply.available,
                              "available_quantity": reply.available_quantity}), 201


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", "8082")))
