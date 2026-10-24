#!/bin/bash
export DOCKER_HOST=unix:///mnt/wsl/docker-desktop/shared-sockets/host-services/docker.proxy.sock
PSQL() { docker exec richangpim-postgres-1 psql -U pim -d ai_pim -tAc "$1"; }
echo "== V-05 pending_action CHECK =="
PSQL "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='pending_action'::regclass AND contype='c'"
echo "== V-12 alembic_version maxlen =="
PSQL "SELECT character_maximum_length FROM information_schema.columns WHERE table_name='alembic_version' AND column_name='version_num'"
echo "== installed extensions =="
PSQL "SELECT extname FROM pg_extension ORDER BY 1"
echo "== available: pg_trgm / vector =="
PSQL "SELECT name FROM pg_available_extensions WHERE name IN ('pg_trgm','vector')"
echo "== PG version =="
PSQL "SHOW server_version"
