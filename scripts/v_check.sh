#!/bin/bash
cd /home/AI-PIM/RiChangPIM || exit 9
echo "== V-01 JWT payload =="
grep -n "payload\|sub\|role\|perms" backend/app/core/security.py | sed -n '1,15p'
grep -n "create_access_token\|perms" backend/app/api/v1/auth.py | head -8

echo "== V-02 envelope/error codes =="
grep -rn '"code"\|exception_handler' backend/app/main.py | head -12
ls backend/app/core/exceptions.py 2>/dev/null || echo "no exceptions.py"

echo "== V-03 pagination =="
grep -rn 'page\|total' backend/app/api/v1/proposals.py | sed -n '1,8p'
grep -rn 'class PageResult\|class Page\|total' backend/app/schemas/product.py | head -5

echo "== V-04 attachment biz hook =="
grep -n "biz\|product_id\|owner" backend/app/models/product.py | sed -n '1,6p'
echo "(Attachment 无 biz 字段则用 junction 表方案)"

echo "== V-05 pending_action constraint name =="
docker compose exec -T postgres psql -U pim -d ai_pim -c "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='pending_action'::regclass AND contype='c';" 2>&1

echo "== V-06 proposal/quotation fields =="
grep -n "total_amount\|status" backend/app/models/sales.py | head -8

echo "== V-07 role dropdown hardcoded =="
grep -rn "roleOptions\|role_code\|options" frontend/src/views/Users.vue | head -8

echo "== V-08 files constants =="
grep -n "_ALLOWED\|1024 \* 1024\|MAX" backend/app/api/v1/files.py | head -8

echo "== V-09 rate limiter key =="
grep -n "key\|def check\|def allow\|f\"" backend/app/core/rate_limiter.py | sed -n '1,10p'

echo "== V-10 vite config =="
cat frontend/vite.config.ts | sed -n '30,50p'
du -sh frontend/dist 2>/dev/null

echo "== V-11 knowledge source scope =="
grep -rn "source_type\|SOURCE" backend/app/models/knowledge.py | head -8
grep -rn "knowledge_source\|source_id" backend/app/api/v1/knowledge_sources.py | head -6

echo "== V-12 alembic_version length =="
docker compose exec -T postgres psql -U pim -d ai_pim -c "SELECT character_maximum_length FROM information_schema.columns WHERE table_name='alembic_version' AND column_name='version_num';" 2>&1

echo "== G0-4.6 nginx body size =="
grep -rn "client_max_body_size\|proxy_read_timeout" docker/nginx/conf.d/ 2>/dev/null || echo "not set"

echo "== G0-4.9 frontend persist =="
grep -rn "persist\|localStorage" frontend/src/stores/*.ts | head -8
ls frontend/src/router* 2>/dev/null; ls frontend/src/stores frontend/src/utils | head -20

echo "== G0-4.12 config fail-closed =="
grep -n "ADMIN_PASSWORD\|required\|ValidationError" backend/app/core/config.py | head -6

echo "== trgm available =="
docker compose exec -T postgres psql -U pim -d ai_pim -c "SELECT name FROM pg_available_extensions WHERE name IN ('pg_trgm','vector');" 2>&1
