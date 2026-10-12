#!/usr/bin/env bash
# Reproduces all README evidence for one version: success, rejection, slow
# inventory (timeout / deadline) and Order Service still healthy afterwards.
#
# Usage (from the repo root, in Git Bash / any bash):
#   scripts/demo.sh rest
#   scripts/demo.sh grpc
set -u
cd "$(dirname "$0")/.."

MODE=${1:-rest}
if [ -x .venv/Scripts/python ]; then PY=.venv/Scripts/python; else PY=.venv/bin/python; fi
mkdir -p logs

if [ "$MODE" = rest ]; then
  INVENTORY=rest.inventory_service; ORDER=rest.order_service; ORDER_PORT=8080
else
  INVENTORY=grpc_version.inventory_server; ORDER=grpc_version.order_service; ORDER_PORT=8082
fi
ORDER_URL=http://127.0.0.1:$ORDER_PORT

INV_PORT=$( [ "$MODE" = rest ] && echo 8081 || echo 50051 )

stop_port() {  # stop whatever process is listening on <port> (Windows or Unix)
  if command -v taskkill > /dev/null; then
    for pid in $(netstat -ano | grep LISTENING | grep ":$1 " | awk '{print $5}' | sort -u); do
      taskkill //PID "$pid" //F > /dev/null
    done
  else
    lsof -ti tcp:"$1" | xargs -r kill
  fi
  for _ in $(seq 1 30); do
    (echo > /dev/tcp/127.0.0.1/"$1") 2>/dev/null || return 0
    sleep 0.2
  done
}
cleanup() { stop_port "$ORDER_PORT"; stop_port "$INV_PORT"; }
trap cleanup EXIT

start() {  # start <module> <logfile> [env assignments...]
  local module=$1 logfile=$2; shift 2
  env "$@" PYTHONUNBUFFERED=1 "$PY" -m "$module" > "logs/$logfile" 2>&1 &
}

wait_for() {  # wait_for <port>
  for _ in $(seq 1 30); do
    (echo > /dev/tcp/127.0.0.1/"$1") 2>/dev/null && return 0
    sleep 0.3
  done
  echo "port $1 never came up" >&2; exit 1
}

order() {  # order <json body>
  echo "\$ curl -X POST $ORDER_URL/orders -H 'Content-Type: application/json' -d '$1'"
  curl -s -w '\n-> HTTP %{http_code} in %{time_total}s\n\n' -X POST "$ORDER_URL/orders" \
    -H 'Content-Type: application/json' -d "$1"
}

section() { printf '\n========== %s ==========\n\n' "$1"; }

section "$MODE: normal inventory"
start "$INVENTORY" "inventory-$MODE.log"
start "$ORDER" "order-$MODE.log"
wait_for "$INV_PORT"; wait_for "$ORDER_PORT"

if [ "$MODE" = grpc ]; then
  echo "\$ python -m grpc_version.client apple 3     # direct gRPC call"
  "$PY" -m grpc_version.client apple 3; echo
  echo "\$ python -m grpc_version.client banana 50"
  "$PY" -m grpc_version.client banana 50; echo
else
  echo "\$ curl -X POST http://127.0.0.1:8081/inventory/check -H 'Content-Type: application/json' -d '{\"item_id\":\"apple\",\"quantity\":3}'"
  curl -s -w '\n-> HTTP %{http_code}\n\n' -X POST http://127.0.0.1:8081/inventory/check \
    -H 'Content-Type: application/json' -d '{"item_id":"apple","quantity":3}'
fi

order '{"item_id":"apple","quantity":3}'
order '{"item_id":"banana","quantity":50}'
order '{"item_id":"mango","quantity":1}'

section "$MODE: slow inventory (INVENTORY_DELAY_SECONDS=5, client limit 2s)"
stop_port "$INV_PORT"
start "$INVENTORY" "inventory-$MODE-slow.log" INVENTORY_DELAY_SECONDS=5
wait_for "$INV_PORT"

order '{"item_id":"apple","quantity":1}'

section "$MODE: Order Service still running after the failure"
echo "\$ curl $ORDER_URL/health"
curl -s -w '\n-> HTTP %{http_code}\n\n' "$ORDER_URL/health"

section "$MODE: inventory back to normal, same Order Service process (no restart)"
stop_port "$INV_PORT"
start "$INVENTORY" "inventory-$MODE-recovered.log"
wait_for "$INV_PORT"
order '{"item_id":"laptop","quantity":1}'

section "$MODE: Order Service log"
grep -v -E 'Serving Flask|Debug mode|WARNING|Running on|CTRL\+C' "logs/order-$MODE.log"
