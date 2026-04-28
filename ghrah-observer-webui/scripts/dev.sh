#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Starting Gateway ==="
(cd "$ROOT_DIR/../ghrah-gateway" && uv run ghrah-gateway) &
GATEWAY_PID=$!

echo "=== Starting Subject ==="
(cd "$ROOT_DIR/../ghrah-subject" && uv run ghrah-subject) &
SUBJECT_PID=$!

echo "=== Starting Observer SPA dev server ==="
(cd "$ROOT_DIR/packages/observer-web" && pnpm dev) &
SPA_PID=$!

echo "=== All services started ==="
echo "  Gateway PID: $GATEWAY_PID"
echo "  Subject PID: $SUBJECT_PID"
echo "  SPA PID: $SPA_PID"
echo ""
echo "Press Ctrl+C to stop all services."

cleanup() {
  echo "Stopping all services..."
  kill $GATEWAY_PID $SUBJECT_PID $SPA_PID 2>/dev/null || true
  wait
  echo "All services stopped."
}

trap cleanup EXIT INT TERM

wait
