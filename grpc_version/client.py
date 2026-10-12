"""Minimal gRPC client that calls InventoryService.CheckInventory directly.

Usage: python -m grpc_version.client <item_id> <quantity> [deadline_seconds]
"""

import sys

import grpc

from proto import inventory_pb2, inventory_pb2_grpc


def main():
    item_id = sys.argv[1] if len(sys.argv) > 1 else "apple"
    quantity = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    deadline = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0

    with grpc.insecure_channel("127.0.0.1:50051") as channel:
        stub = inventory_pb2_grpc.InventoryServiceStub(channel)
        request = inventory_pb2.CheckInventoryRequest(item_id=item_id, quantity=quantity)
        print(f"request:  {request}".replace("\n", " "))
        try:
            reply = stub.CheckInventory(request, timeout=deadline)
            print(f"response: {reply}".replace("\n", " "))
        except grpc.RpcError as e:
            print(f"error:    {e.code().name}: {e.details()}")


if __name__ == "__main__":
    main()
