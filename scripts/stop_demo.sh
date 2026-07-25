#!/usr/bin/env bash
set -euo pipefail

PID_FILE="/tmp/ai-pim-demo-server.pid"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" >/dev/null 2>&1; then
    kill "$PID"
    echo "==> stopped demo server (pid $PID)"
  else
    echo "==> demo server pid file exists but process is gone"
  fi
  rm -f "$PID_FILE"
else
  echo "==> no demo server pid file found"
fi
