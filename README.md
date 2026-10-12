# CMPE-273 Module 3: REST & gRPC Service Contracts

The same **Order → Inventory** interaction, implemented twice in Python:

| | REST version | gRPC version |
|---|---|---|
| Inventory Service | `rest/inventory_service.py` (Flask, port **8081**) | `grpc_version/inventory_server.py` (gRPC, port **50051**) |
| Order Service | `rest/order_service.py` (Flask, port **8080**) | `grpc_version/order_service.py` (Flask, port **8082**) |
| Contract | `POST /inventory/check` with JSON | `proto/inventory.proto` |
| Time limit on Order → Inventory | `requests` **timeout = 2 s** | gRPC **deadline = 2 s** |

Both Order Services expose the same client-facing API (`POST /orders`), so the only thing that changes between the two versions is how the Order Service talks to Inventory. The stock table and business rules live in `common/stock.py` and are shared by both Inventory Services:

| item_id | in stock |
|---|---|
| `apple` | 10 |
| `banana` | 5 |
| `laptop` | 2 |

## Repository layout

```
proto/inventory.proto           gRPC service contract (+ generated inventory_pb2*.py)
common/stock.py                 shared stock table, availability check, simulated delay
rest/inventory_service.py       REST Inventory Service
rest/order_service.py           REST Order Service (HTTP client with timeout)
grpc_version/inventory_server.py  gRPC Inventory Service
grpc_version/order_service.py     Order Service calling Inventory over gRPC (with deadline)
grpc_version/client.py            small gRPC client for calling Inventory directly
scripts/demo.sh                 reproduces all evidence below
evidence/                       captured output of scripts/demo.sh
```

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

The generated gRPC code (`proto/inventory_pb2.py`, `proto/inventory_pb2_grpc.py`) is committed. To regenerate it after editing the `.proto` file:

```bash
python -m grpc_tools.protoc -I . --python_out=. --grpc_python_out=. proto/inventory.proto
```

All commands below are run **from the repository root**, in separate terminals, with the virtual environment activated.

## Running the REST version

```bash
python -m rest.inventory_service     # terminal 1, port 8081
python -m rest.order_service         # terminal 2, port 8080
```

```bash
curl -X POST http://127.0.0.1:8080/orders -H "Content-Type: application/json" -d '{"item_id":"apple","quantity":3}'
```

| Situation | HTTP status from Order Service |
|---|---|
| Item available | `201 Created` |
| Malformed body | `400 Bad Request` |
| Unknown item | `404 Not Found` |
| Not enough stock | `409 Conflict` |
| Inventory unreachable | `503 Service Unavailable` |
| Inventory slower than the timeout | `504 Gateway Timeout` |

The timeout is configurable with `INVENTORY_TIMEOUT_SECONDS` (default `2.0`).

## Running the gRPC version

```bash
python -m grpc_version.inventory_server   # terminal 1, port 50051
python -m grpc_version.order_service      # terminal 2, port 8082
```

```bash
# Through the Order Service (HTTP in, gRPC to Inventory)
curl -X POST http://127.0.0.1:8082/orders -H "Content-Type: application/json" -d '{"item_id":"apple","quantity":3}'

# Or call the Inventory gRPC service directly
python -m grpc_version.client apple 3
```

| Situation | gRPC status from Inventory | HTTP status from Order Service |
|---|---|---|
| Item available | `OK` | `201` |
| Malformed request | `INVALID_ARGUMENT` | `400` |
| Unknown item | `NOT_FOUND` | `404` |
| Not enough stock | `FAILED_PRECONDITION` | `409` |
| Inventory unreachable | `UNAVAILABLE` | `503` |
| Inventory slower than the deadline | `DEADLINE_EXCEEDED` | `504` |

The deadline is configurable with `INVENTORY_DEADLINE_SECONDS` (default `2.0`).

## Simulating a slow Inventory Service

Both Inventory Services read `INVENTORY_DELAY_SECONDS` and sleep that long before answering. Start Inventory with a delay longer than the 2 s limit:

```bash
# macOS/Linux/Git Bash
INVENTORY_DELAY_SECONDS=5 python -m rest.inventory_service
INVENTORY_DELAY_SECONDS=5 python -m grpc_version.inventory_server

# Windows PowerShell
$env:INVENTORY_DELAY_SECONDS=5; python -m rest.inventory_service
```

To reproduce everything in this README automatically (bash / Git Bash):

```bash
scripts/demo.sh rest
scripts/demo.sh grpc
```

---

## Evidence

Full output: [`evidence/rest_demo.txt`](evidence/rest_demo.txt) and [`evidence/grpc_demo.txt`](evidence/grpc_demo.txt).

### 1. Successful REST request and response

```
$ curl -X POST http://127.0.0.1:8081/inventory/check -H 'Content-Type: application/json' -d '{"item_id":"apple","quantity":3}'
{"available":true,"available_quantity":10,"item_id":"apple","requested_quantity":3}
-> HTTP 200

$ curl -X POST http://127.0.0.1:8080/orders -H 'Content-Type: application/json' -d '{"item_id":"apple","quantity":3}'
{"inventory":{"available":true,"available_quantity":10,"item_id":"apple","requested_quantity":3},"item_id":"apple","order_id":"39ce23ed","quantity":3,"status":"CONFIRMED"}
-> HTTP 201 in 0.006171s
```

Rejections use proper status codes:

```
$ curl -X POST http://127.0.0.1:8080/orders -H 'Content-Type: application/json' -d '{"item_id":"banana","quantity":50}'
{"inventory":{"available":false,"available_quantity":5,"error":"insufficient stock","item_id":"banana","requested_quantity":50},"item_id":"banana","quantity":50,"reason":"insufficient stock","status":"REJECTED"}
-> HTTP 409 in 0.003167s

$ curl -X POST http://127.0.0.1:8080/orders -H 'Content-Type: application/json' -d '{"item_id":"mango","quantity":1}'
{"inventory":{"available":false,"error":"unknown item","item_id":"mango"},"item_id":"mango","quantity":1,"reason":"unknown item","status":"REJECTED"}
-> HTTP 404 in 0.002931s
```

### 2. Successful gRPC request and response

```
$ python -m grpc_version.client apple 3     # direct gRPC call
request:  item_id: "apple" quantity: 3
response: item_id: "apple" requested_quantity: 3 available_quantity: 10 available: true

$ curl -X POST http://127.0.0.1:8082/orders -H 'Content-Type: application/json' -d '{"item_id":"apple","quantity":3}'
{"inventory":{"available":true,"available_quantity":10},"item_id":"apple","order_id":"391a8809","quantity":3,"status":"CONFIRMED"}
-> HTTP 201 in 0.003032s
```

Unavailable items return gRPC error statuses:

```
$ python -m grpc_version.client banana 50
error:    FAILED_PRECONDITION: insufficient stock for 'banana': requested 50, available 5

$ curl -X POST http://127.0.0.1:8082/orders -H 'Content-Type: application/json' -d '{"item_id":"mango","quantity":1}'
{"grpc_status":"NOT_FOUND","item_id":"mango","quantity":1,"reason":"unknown item 'mango'","status":"REJECTED"}
-> HTTP 404 in 0.002072s
```

### 3. REST timeout handling

Inventory restarted with `INVENTORY_DELAY_SECONDS=5`; the Order Service gives up after its 2 s timeout and returns a clean `504`:

```
$ curl -X POST http://127.0.0.1:8080/orders -H 'Content-Type: application/json' -d '{"item_id":"apple","quantity":1}'
{"error":"inventory service timed out after 2.0s","status":"FAILED"}
-> HTTP 504 in 2.019751s
```

Order Service log:

```
2026-10-11 22:23:55,002 [order-rest] inventory timed out after 2.0s (item=apple)
2026-10-11 22:23:55,003 [order-rest] 127.0.0.1 - - [11/Oct/2026 22:23:55] "POST /orders HTTP/1.1" 504 -
```

### 4. gRPC deadline handling

Same 5 s delay; the 2 s deadline expires and the call fails with `DEADLINE_EXCEEDED`, mapped to `504`:

```
$ curl -X POST http://127.0.0.1:8082/orders -H 'Content-Type: application/json' -d '{"item_id":"apple","quantity":1}'
{"error":"Deadline Exceeded","grpc_status":"DEADLINE_EXCEEDED","status":"FAILED"}
-> HTTP 504 in 2.014363s
```

Order Service log:

```
2026-10-11 22:24:14,627 [order-grpc] inventory call failed: DEADLINE_EXCEEDED after 2.0s deadline (item=apple)
2026-10-11 22:24:14,628 [order-grpc] 127.0.0.1 - - [11/Oct/2026 22:24:14] "POST /orders HTTP/1.1" 504 -
```

### 5. Order Service keeps running after the failures

Right after each failure the **same** Order Service process (never restarted) still answers health checks, and once Inventory is back to normal it confirms orders again.

REST:

```
$ curl http://127.0.0.1:8080/health
{"service":"order-rest","status":"ok"}
-> HTTP 200

$ curl -X POST http://127.0.0.1:8080/orders -H 'Content-Type: application/json' -d '{"item_id":"laptop","quantity":1}'
{"inventory":{"available":true,"available_quantity":2,"item_id":"laptop","requested_quantity":1},"item_id":"laptop","order_id":"d1e34607","quantity":1,"status":"CONFIRMED"}
-> HTTP 201 in 0.017646s
```

gRPC:

```
$ curl http://127.0.0.1:8082/health
{"service":"order-grpc","status":"ok"}
-> HTTP 200

$ curl -X POST http://127.0.0.1:8082/orders -H 'Content-Type: application/json' -d '{"item_id":"laptop","quantity":1}'
{"inventory":{"available":true,"available_quantity":2},"item_id":"laptop","order_id":"34d998d2","quantity":1,"status":"CONFIRMED"}
-> HTTP 201 in 0.003041s
```

The full Order Service logs in `evidence/` show the success → timeout → health → success sequence in a single process run.

---

## REST vs gRPC: what I observed

With gRPC the contract came first: I wrote `inventory.proto`, generated the client and server code, and the request/response types were enforced by the generated classes. In REST, the contract was only an agreement about JSON field names that I had to validate by hand in both services. Error handling also felt different. REST spreads failures across HTTP status codes and a JSON error body, while gRPC has a fixed set of status codes (`NOT_FOUND`, `FAILED_PRECONDITION`, `DEADLINE_EXCEEDED`), so the Order Service could map them with a single lookup table. The REST timeout is purely a client-side setting in `requests`; the gRPC deadline is sent with the call, so both client and server know when the request expires. REST was much easier to test and debug because any `curl` command works, whereas gRPC needed a generated stub (`grpc_version/client.py`) just to send one request. Finally, on Windows the REST client's `localhost` lookup tried IPv6 first and added about 2 s to every call, almost the whole timeout, which showed how sensitive a timeout is to small network details.
