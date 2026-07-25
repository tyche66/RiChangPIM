#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="/tmp/ai-pim-demo-server.pid"
PORT="${PIM_DEMO_PORT:-5173}"
HOST="${PIM_DEMO_HOST:-0.0.0.0}"
BACKEND_URL="${PIM_DEMO_BACKEND:-http://127.0.0.1:8000}"

cd "$ROOT"

if [ ! -d "$ROOT/frontend/dist" ]; then
  echo "ERROR: frontend/dist not found. Run 'cd frontend && npm run build' first." >&2
  exit 1
fi

if curl -fsS "${BACKEND_URL%/}/api/v1/health" >/dev/null 2>&1; then
  echo "==> backend OK: ${BACKEND_URL%/}/api/v1/health"
else
  echo "WARN: backend health check failed: ${BACKEND_URL%/}/api/v1/health" >&2
fi

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" >/dev/null 2>&1; then
  echo "==> demo server already running (pid $(cat "$PID_FILE"))"
else
  echo "==> starting demo server on http://${HOST}:${PORT}"
  nohup env \
    PIM_DEMO_ROOT="$ROOT/frontend/dist" \
    PIM_DEMO_PORT="$PORT" \
    PIM_DEMO_HOST="$HOST" \
    PIM_DEMO_BACKEND="$BACKEND_URL" \
    node "$ROOT/scripts/pim-demo-server.mjs" \
    > /tmp/ai-pim-demo-server.log 2>&1 &
  echo $! > "$PID_FILE"
fi

sleep 1

if curl -fsS "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
  echo "==> demo server is ready: http://127.0.0.1:${PORT}/"
else
  echo "ERROR: demo server failed to start. See /tmp/ai-pim-demo-server.log" >&2
  exit 1
fi

echo "==> expected Windows mapping: 3001 -> 198.18.0.1:${PORT}"
