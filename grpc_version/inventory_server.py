"""gRPC Inventory Service (port 50051). Implements proto/inventory.proto.

Errors are returned as gRPC status codes:
  INVALID_ARGUMENT    - malformed request
  NOT_FOUND           - unknown item
  FAILED_PRECONDITION - not enough stock
"""

import logging
import os
from concurrent import futures

import grpc

from common import stock
from proto import inventory_pb2, inventory_pb2_grpc

logging.basicConfig(level=logging.INFO, format="%(asctime)s [inventory-grpc] %(message)s")
log = logging.getLogger(__name__)


class InventoryService(inventory_pb2_grpc.InventoryServiceServicer):
    def CheckInventory(self, request, context):
        item_id, quantity = request.item_id, request.quantity
        if not item_id or quantity <= 0:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                          "item_id is required and quantity must be positive")

        delay = stock.simulated_delay()
        if delay:
            log.info("simulated delay of %.1fs applied", delay)

        try:
            available = stock.check(item_id, quantity)
        except stock.UnknownItem:
            log.info("check item=%s qty=%d -> NOT_FOUND", item_id, quantity)
            context.abort(grpc.StatusCode.NOT_FOUND, f"unknown item '{item_id}'")
        except stock.InsufficientStock as e:
            log.info("check item=%s qty=%d -> FAILED_PRECONDITION (have %d)", item_id, quantity, e.available)
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          f"insufficient stock for '{item_id}': requested {quantity}, available {e.available}")

        log.info("check item=%s qty=%d -> OK (have %d)", item_id, quantity, available)
        return inventory_pb2.CheckInventoryResponse(
            item_id=item_id, requested_quantity=quantity,
            available_quantity=available, available=True)


def serve():
    port = os.environ.get("PORT", "50051")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    inventory_pb2_grpc.add_InventoryServiceServicer_to_server(InventoryService(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info("listening on port %s", port)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
