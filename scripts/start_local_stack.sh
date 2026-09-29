#!/usr/bin/env bash
# RiChangPIM 本机前后端一键启动脚本（非 Docker）。
#
# 拓扑（与项目生产路由一致，端口做了本机适配）：
#   nginx :888  -> portal/dist（/）、frontend/dist（/admin/）、/api 反代 127.0.0.1:8000
#   backend :8000（backend/venv + uvicorn）
#   postgres :5433（本机原生 PG18，ai_pim 恢复自 backups/manual_20260731T151052.sqlc）
#   redis :6379、minio :9100（对象存储，bucket: ai-pim）
#
# 用法: scripts/start_local_stack.sh {start|stop|restart|status}
set -euo pipefail

BASE_DIR="/home/AI-PIM/RiChangPIM"
RUNTIME_DIR="${RUNTIME_DIR:-/var/lib/richangpim-local}"
LOG_DIR="$RUNTIME_DIR/logs"
NGINX_CONF="$RUNTIME_DIR/nginx.conf"
NGINX_PID="$RUNTIME_DIR/nginx.pid"

PG_BIN="/usr/lib/postgresql/18/bin"
PGDATA="/var/lib/postgresql/18/main"
PGCONF="/etc/postgresql/18/main/postgresql.conf"
PG_PORT=5433
REDIS_PORT=6379
MINIO_PORT=9100
BACKEND_PORT=8000
HTTP_PORT=888

DB_URL="${DATABASE_URL:-postgresql://pim:pim_local_888@127.0.0.1:5433/ai_pim}"
MINIO_USER="${MINIO_USER:-gominio_9d2214e1}"
MINIO_PASS="${MINIO_PASS:-go_eeb39d34376603e2fe05cb39a04d7e15}"
MINIO_DATA="${MINIO_DATA:-/var/lib/docker/volumes/richangpim_go_minio_data_20260716/_data}"
VENV_PY="$BASE_DIR/backend/venv/bin/python"
BACKEND_DIR="$BASE_DIR/backend"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

env_get() {
  local key="$1" file="$2" fallback="${3:-}"
  local v
  v="$(grep -E "^${key}=" "$file" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  echo "${v:-$fallback}"
}

# 优先取 shell 环境变量，其次根 .env。用于把 AI_* 配置传给 backend
# （backend 自身的 backend/.env 是 AI_ADAPTER=none 的模板值，不能覆盖真实配置）。
env_or_file() {
  local key="$1" fallback="${2:-}"
  if [ -n "${!key:-}" ]; then
    printf '%s' "${!key}"
  else
    env_get "$key" "$BASE_DIR/.env" "$fallback"
  fi
}

port_open() { ss -ltn 2>/dev/null | grep -q ":$1 "; }

http_ok() { curl -sf -m 3 "$1" >/dev/null 2>&1; }

ensure_runtime() {
  mkdir -p "$LOG_DIR"
  touch "$LOG_DIR/postgres.log" "$LOG_DIR/backend.log" "$LOG_DIR/minio.log" "$LOG_DIR/redis.log"
  chown postgres:postgres "$LOG_DIR/postgres.log"
  chmod 666 "$LOG_DIR"/*.log
}

write_nginx_conf() {
  cat > "$NGINX_CONF" <<EOF
worker_processes 1;
pid $NGINX_PID;
error_log $LOG_DIR/nginx-error.log warn;

events { worker_connections 1024; }

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    access_log $LOG_DIR/nginx-access.log;
    sendfile on;
    keepalive_timeout 65;
    client_max_body_size 100M;

    server {
        listen $HTTP_PORT;
        server_name _;
        absolute_redirect off;

        location = /admin { return 301 /admin/; }

        location /admin/ {
            alias $BASE_DIR/frontend/dist/;
            try_files \$uri \$uri/ /admin/index.html;
        }

        location / {
            root $BASE_DIR/portal/dist;
            try_files \$uri \$uri/ /index.html;
        }

        location /api/ {
            proxy_pass http://127.0.0.1:$BACKEND_PORT;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_set_header Authorization \$http_authorization;
        }

        location /health/ {
            proxy_pass http://127.0.0.1:$BACKEND_PORT;
            proxy_set_header Host \$host;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        }

        location /docs { proxy_pass http://127.0.0.1:$BACKEND_PORT; }
        location /openapi.json { proxy_pass http://127.0.0.1:$BACKEND_PORT; }
    }
}
EOF
}

start_postgres() {
  if su postgres -c "psql -h /var/run/postgresql -p $PG_PORT -U postgres -tAc 'select 1'" >/dev/null 2>&1; then
    log "postgres :$PG_PORT 已在运行"
    return 0
  fi
  mkdir -p /var/run/postgresql && chown postgres:postgres /var/run/postgresql
  if [ -f "$PGDATA/postmaster.pid" ]; then
    local pid; pid="$(head -1 "$PGDATA/postmaster.pid" 2>/dev/null || true)"
    if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$PGDATA/postmaster.pid"
      log "清理残留 postmaster.pid"
    fi
  fi
  log "启动 postgres :$PG_PORT ..."
  su postgres -c "$PG_BIN/pg_ctl -D $PGDATA -o '-c config_file=$PGCONF -p $PG_PORT -k /var/run/postgresql -c listen_addresses=127.0.0.1' -l $LOG_DIR/postgres.log start"
}

start_redis() {
  if redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then
    log "redis :$REDIS_PORT 已在运行"
    return 0
  fi
  log "启动 redis :$REDIS_PORT ..."
  redis-server --daemonize yes --bind 127.0.0.1 --port "$REDIS_PORT" \
    --dir /tmp --save '' --appendonly no --logfile "$LOG_DIR/redis.log"
  for _ in $(seq 1 10); do redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1 && break; sleep 0.5; done
}

minio_bin() {
  if command -v minio >/dev/null 2>&1; then command -v minio; return; fi
  ls /var/lib/docker/containerd/daemon/io.containerd.snapshotter.v1.overlayfs/snapshots/*/fs/usr/bin/minio 2>/dev/null | head -1
}

start_minio() {
  if http_ok "http://127.0.0.1:$MINIO_PORT/minio/health/live"; then
    log "minio :$MINIO_PORT 已在运行"
    return 0
  fi
  local bin; bin="$(minio_bin)"
  [ -n "$bin" ] || { log "错误: 找不到 minio 可执行文件"; return 1; }
  log "启动 minio :$MINIO_PORT (bin: $bin) ..."
  setsid nohup env MINIO_ROOT_USER="$MINIO_USER" MINIO_ROOT_PASSWORD="$MINIO_PASS" \
    "$bin" server "$MINIO_DATA" --address "127.0.0.1:$MINIO_PORT" --console-address "127.0.0.1:9101" \
    >> "$LOG_DIR/minio.log" 2>&1 < /dev/null &
  for _ in $(seq 1 20); do http_ok "http://127.0.0.1:$MINIO_PORT/minio/health/live" && break; sleep 0.5; done
}

start_backend() {
  if http_ok "http://127.0.0.1:$BACKEND_PORT/api/v1/health"; then
    log "backend :$BACKEND_PORT 已在运行"
    return 0
  fi
  log "启动 backend :$BACKEND_PORT ..."
  (
    cd "$BACKEND_DIR"
    setsid nohup env \
      DATABASE_URL="$DB_URL" \
      REDIS_URL="redis://127.0.0.1:$REDIS_PORT/0" \
      MINIO_ENDPOINT="127.0.0.1:$MINIO_PORT" \
      MINIO_ACCESS_KEY="$MINIO_USER" \
      MINIO_SECRET_KEY="$MINIO_PASS" \
      MINIO_BUCKET="ai-pim" \
      MINIO_SECURE=false \
      AI_ADAPTER="$(env_or_file AI_ADAPTER none)" \
      AI_API_URL="$(env_or_file AI_API_URL '')" \
      AI_API_KEY="$(env_or_file AI_API_KEY '')" \
      AI_CHAT_MODEL="$(env_or_file AI_CHAT_MODEL gpt-4o-mini)" \
      AI_EMBEDDING_MODEL="$(env_or_file AI_EMBEDDING_MODEL text-embedding-3-small)" \
      AI_EMBEDDING_DIM="$(env_or_file AI_EMBEDDING_DIM 1536)" \
      AI_EMBEDDING_API_URL="$(env_or_file AI_EMBEDDING_API_URL '')" \
      AI_EMBEDDING_API_KEY="$(env_or_file AI_EMBEDDING_API_KEY '')" \
      AI_TIMEOUT="$(env_or_file AI_TIMEOUT 30)" \
      AI_TOOL_PLANNING_TIMEOUT="$(env_or_file AI_TOOL_PLANNING_TIMEOUT 8)" \
      APP_ENV="${APP_ENV:-production}" \
      JWT_SECRET="$(env_get JWT_SECRET "$BASE_DIR/.env" local_dev_jwt_secret_change_me_ai_pim_20260717)" \
      ADMIN_USERNAME="$(env_get ADMIN_USERNAME "$BASE_DIR/.env" admin)" \
      ADMIN_PASSWORD="$(env_get ADMIN_PASSWORD "$BASE_DIR/.env" RiChangPIM888)" \
      "$VENV_PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" \
      >> "$LOG_DIR/backend.log" 2>&1 < /dev/null &
  )
  for _ in $(seq 1 30); do http_ok "http://127.0.0.1:$BACKEND_PORT/api/v1/health" && break; sleep 1; done
  http_ok "http://127.0.0.1:$BACKEND_PORT/api/v1/health"
}

start_nginx() {
  if [ -f "$NGINX_PID" ] && kill -0 "$(cat "$NGINX_PID")" 2>/dev/null; then
    log "nginx :$HTTP_PORT 已在运行，重载配置"
    nginx -s reload -c "$NGINX_CONF" -p "$RUNTIME_DIR" 2>/dev/null || true
    return 0
  fi
  log "启动 nginx :$HTTP_PORT ..."
  write_nginx_conf
  nginx -c "$NGINX_CONF" -p "$RUNTIME_DIR"
  for _ in $(seq 1 10); do http_ok "http://127.0.0.1:$HTTP_PORT/" && break; sleep 0.5; done
}

stop_nginx() {
  if [ -f "$NGINX_PID" ] && kill -0 "$(cat "$NGINX_PID")" 2>/dev/null; then
    log "停止 nginx ..."; nginx -s quit -c "$NGINX_CONF" -p "$RUNTIME_DIR" 2>/dev/null || true
  else
    log "nginx 未在运行"
  fi
}

stop_backend() {
  local pids; pids="$(pgrep -f "uvicorn app.main:app.*--port $BACKEND_PORT" || true)"
  if [ -n "$pids" ]; then log "停止 backend ..."; kill $pids 2>/dev/null || true; else log "backend 未在运行"; fi
}

stop_minio() {
  local pids; pids="$(pgrep -f "minio server $MINIO_DATA" || true)"
  if [ -n "$pids" ]; then log "停止 minio ..."; kill $pids 2>/dev/null || true; else log "minio 未在运行"; fi
}

stop_redis() {
  if redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then
    log "停止 redis ..."; redis-cli -p "$REDIS_PORT" shutdown nosave >/dev/null 2>&1 || true
  else
    log "redis 未在运行"
  fi
}

stop_postgres() {
  if su postgres -c "$PG_BIN/pg_ctl -D $PGDATA status" >/dev/null 2>&1; then
    log "停止 postgres ..."; su postgres -c "$PG_BIN/pg_ctl -D $PGDATA -m fast stop"
  else
    log "postgres 未在运行"
  fi
}

cmd_start() {
  ensure_runtime
  start_postgres
  start_redis
  start_minio
  start_backend
  start_nginx
  cmd_status
}

cmd_stop() {
  stop_nginx
  stop_backend
  stop_minio
  stop_redis
  stop_postgres
}

pg_state() {
  if su postgres -c "$PG_BIN/pg_ctl -D $PGDATA status" >/dev/null 2>&1; then echo UP; else echo DOWN; fi
}

cmd_status() {
  echo "----------------------------------------------"
  echo " postgres :$PG_PORT  $(pg_state)"
  echo " redis    :$REDIS_PORT  $(redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1 && echo UP || echo DOWN)"
  echo " minio    :$MINIO_PORT  $(http_ok "http://127.0.0.1:$MINIO_PORT/minio/health/live" && echo UP || echo DOWN)"
  echo " backend  :$BACKEND_PORT  $(http_ok "http://127.0.0.1:$BACKEND_PORT/api/v1/health" && echo UP || echo DOWN)"
  echo " nginx    :$HTTP_PORT  $(http_ok "http://127.0.0.1:$HTTP_PORT/" && echo UP || echo DOWN)"
  echo "----------------------------------------------"
  echo " 门户:   http://127.0.0.1:$HTTP_PORT/"
  echo " 后台:   http://127.0.0.1:$HTTP_PORT/admin/"
  echo " 健康:   http://127.0.0.1:$HTTP_PORT/api/v1/health"
  echo " 日志:   $LOG_DIR/"
}

case "${1:-start}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  status)  cmd_status ;;
  *) echo "用法: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
