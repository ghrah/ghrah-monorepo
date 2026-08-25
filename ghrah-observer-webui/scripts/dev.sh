#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Mock mode: ./scripts/dev.sh --mock [--scenario demo] [--port 4113]
# Starts only the protocol-level mock server + SPA; the SPA connects to the
# mock via VITE_GHRAH_SUBJECT_WS_URL. No Core/Subject needed.
if [[ "${1:-}" == "--mock" ]]; then
  shift
  SCENARIO="demo"
  PORT="4113"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --scenario) SCENARIO="$2"; shift 2 ;;
      --port) PORT="$2"; shift 2 ;;
      *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
  done

  echo "=== Starting Mock Server (scenario: $SCENARIO, port: $PORT) ==="
  (cd "$ROOT_DIR/packages/mock-server" && pnpm build >/dev/null && node dist/cli.js --port "$PORT" --scenario "$SCENARIO") &
  MOCK_PID=$!

  echo "=== Starting Observer SPA dev server (WS -> mock) ==="
  (cd "$ROOT_DIR/packages/observer-web" && VITE_GHRAH_SUBJECT_WS_URL="ws://localhost:$PORT/ws" pnpm dev) &
  SPA_PID=$!

  echo "=== Mock mode started ==="
  echo "  Mock server PID: $MOCK_PID (ws://localhost:$PORT/ws, scenario: $SCENARIO)"
  echo "  SPA PID: $SPA_PID"
  echo ""
  echo "Press Ctrl+C to stop all services."

  cleanup_mock() {
    echo "Stopping services..."
    kill $MOCK_PID $SPA_PID 2>/dev/null || true
    wait
    echo "All services stopped."
  }
  trap cleanup_mock EXIT INT TERM
  wait
fi

echo "=== Starting Core server ==="
(cd "$ROOT_DIR/../ghrah-core" && uv run python -m ghrah.core.server) &
CORE_PID=$!

sleep 3s

echo "=== Starting Subject ==="
(cd "$ROOT_DIR/../ghrah-subject" && uv run ghrah-subject) &
SUBJECT_PID=$!

echo "=== Starting Observer SPA dev server ==="
(cd "$ROOT_DIR/packages/observer-web" && pnpm dev) &
SPA_PID=$!

echo "=== All services started ==="
echo "  Core server PID: $CORE_PID"
echo "  Subject PID: $SUBJECT_PID"
echo "  SPA PID: $SPA_PID"
echo ""
echo "Press Ctrl+C to stop all services."

cleanup() {
  echo "Stopping all services..."
  kill $CORE_PID $SUBJECT_PID $SPA_PID 2>/dev/null || true
  wait
  echo "All services stopped."
}

trap cleanup EXIT INT TERM

wait
