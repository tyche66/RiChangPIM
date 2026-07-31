#!/usr/bin/env bash
# 停 demo server。默认只停 5173 那一个实例。
#
# 为什么要按端口停：demo server 可以同时跑多个实例（比如 5173 指向生产后端、5180
# 指向本地开发后端）。老版本这里是「找到所有 pim-demo-server.mjs 全杀」，一旦有人
# 只想停自己那个，就会顺手把别人正在用的实例（甚至外网隧道正对着的那个）带走。
#
# 用法：
#   scripts/stop_demo.sh                 # 停 5173
#   PIM_DEMO_PORT=5180 scripts/stop_demo.sh
#   scripts/stop_demo.sh --all           # 真的要全停
set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)/pim-demo-server.mjs"
ALL=0
if [ "${1:-}" = "--all" ]; then
  ALL=1
fi
PORT="${PIM_DEMO_PORT:-5173}"

stop_pid() {
  local pid="$1"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid"
    echo "==> stopped demo server (pid $pid)"
    return 0
  fi
  return 1
}

# 进程 exec 成 node 之后命令行里看不到 PIM_DEMO_PORT，只能从 /proc 读环境。
port_of() {
  local pid="$1"
  tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null |
    sed -n 's/^PIM_DEMO_PORT=//p' | head -1
}

STOPPED=0
for pid_file in "/tmp/ai-pim-demo-server-${PORT}.pid" /tmp/ai-pim-demo-server.pid; do
  [ "$ALL" -eq 1 ] && break
  if [ -f "$pid_file" ]; then
    PID="$(cat "$pid_file")"
    if [ -n "$PID" ] && stop_pid "$PID"; then
      STOPPED=1
    else
      echo "==> pid file $pid_file 里的进程已经没了"
    fi
    rm -f "$pid_file"
  fi
done

CANDIDATES="$(ps -eo pid=,args= | grep "pim-demo-server.mjs" | grep -v grep | awk '{print $1}')"
for pid in $CANDIDATES; do
  if [ "$ALL" -eq 1 ]; then
    stop_pid "$pid" && STOPPED=1 || true
    continue
  fi
  p="$(port_of "$pid")"
  # 环境里读不到端口（老实例）时按默认 5173 处理。
  if [ "${p:-5173}" = "$PORT" ]; then
    stop_pid "$pid" && STOPPED=1 || true
  else
    echo "==> 跳过 pid $pid（PIM_DEMO_PORT=${p}，不是 ${PORT}）"
  fi
done

if [ "$STOPPED" -eq 0 ]; then
  echo "==> 没有需要停的 demo server（PORT=${PORT}${ALL:+, all=$ALL}）"
fi
