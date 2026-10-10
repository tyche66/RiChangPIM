#!/bin/bash
# Phase 0.5 起用：一次性集成测试库容器（设计文档 docs/10 附录 D）（PG16 + pgvector），绑定 127.0.0.1:5432，库名含 test。
# 绝不挂载生产卷、绝不连 ai_pim。
export DOCKER_HOST=unix:///mnt/wsl/docker-desktop/shared-sockets/host-services/docker.proxy.sock
set -e
if ss -ltn 2>/dev/null | grep -q '127.0.0.1:5432'; then
  echo "PORT_5432_BUSY: 先确认是什么进程在用（不得动生产）"; exit 2
fi
docker rm -f pim_pgtest >/dev/null 2>&1 || true
docker run -d --name pim_pgtest \
  -e POSTGRES_USER=pim -e POSTGRES_PASSWORD=pim_password -e POSTGRES_DB=ai_pim_test \
  -p 127.0.0.1:5432:5432 pgvector/pgvector:pg16 postgres -c max_connections=100
for i in $(seq 1 30); do
  if docker exec pim_pgtest pg_isready -U pim -d ai_pim_test >/dev/null 2>&1; then break; fi
  sleep 1
done
docker exec pim_pgtest psql -U pim -d ai_pim_test -c 'CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'
echo "PGTEST_READY"
