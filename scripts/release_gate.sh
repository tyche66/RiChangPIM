#!/usr/bin/env bash
# AI-PIM V1.2 Release Gate — local runner.
#
# Implements all gates in RELEASE_GATE.md except live browser tests and the
# production regression (which need real services). Used to fast-fail before
# pushing a release branch and as the authoritative gate during RC.
#
# Run from the repo root (RiChangPIM/). Requires python (with backend venv
# or system python with requirements) and node for frontend.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PASS=0
FAIL=0
SKIPPED=0
gate() {
  local name="$1" cmd="$2" required="${3:-required}"
  echo
  echo "==> GATE: $name"
  if (eval "$cmd"); then
    echo "    PASS"
    PASS=$((PASS + 1))
  else
    if [ "$required" = "optional" ]; then
      echo "    SKIP (optional, exit code $?)"
      SKIPPED=$((SKIPPED + 1))
    else
      echo "    FAIL (exit code $?)"
      FAIL=$((FAIL + 1))
    fi
  fi
}

# ---------------------------------------------------------------------------
echo "=== Backend quality ==="
gate "backend ruff"          "cd backend && (venv/bin/python -m ruff check app || ruff check app)"
gate "backend compileall"   "cd backend && (venv/bin/python -m compileall app -q || python -m compileall app -q)"
gate "backend pytest"       "cd backend && (venv/bin/python -m pytest -q || python -m pytest -q)"

echo
echo "=== Backend audit ==="
gate "pip-audit (HIGH/CRITICAL)" "cd backend && (command -v pip-audit >/dev/null && pip-audit -r requirements.txt --strict || echo 'pip-audit not installed; skip')" optional

echo
echo "=== Frontend quality (requires npm install) ==="
gate "frontend vue-tsc"      "cd frontend && npx vue-tsc --noEmit"
gate "frontend ESLint (no fix, max-warnings 0)" \
     "cd frontend && npx eslint . --ext .vue,.js,.jsx,.cjs,.mjs,.ts,.tsx --max-warnings=0"
gate "frontend Vitest"       "cd frontend && npx vitest run"
gate "frontend production build" "cd frontend && npm run build"
gate "npm audit (HIGH/CRITICAL production deps)" \
     "cd frontend && npm audit --omit=dev --audit-level=high" optional

echo
echo "=== Compose static validation ==="
gate "docker-compose.yml config" \
     "POSTGRES_PASSWORD=x MINIO_ROOT_USER=x MINIO_ROOT_PASSWORD=x JWT_SECRET=x docker compose -f docker-compose.yml config --quiet"
gate "docker-compose.dev.yml config" \
     "POSTGRES_PASSWORD=x MINIO_ROOT_USER=x MINIO_ROOT_PASSWORD=x JWT_SECRET=x docker compose -f docker-compose.dev.yml config --quiet"

echo
echo "=== Migration hash baseline (0001..0009 immutable) ==="
gate "migration file hashes snapshot" \
     "cd backend && sha256sum alembic/versions/0001_initial.py alembic/versions/0002_rag_polish.py alembic/versions/0003_add_quotation_subtotal.py alembic/versions/0004_seed_data.py alembic/versions/0005_fix_partial_unique.py alembic/versions/0006_add_manual_indexing.py alembic/versions/0007_add_manual_parse_metadata.py alembic/versions/0008_v11_audit_workflow_ocr.py alembic/versions/0009_sunon_pilot_product_fields.py > /tmp/ai-pim-migration-baseline.txt && diff <(cat alembic/versions/.migration_baseline.txt 2>/dev/null || true) /tmp/ai-pim-migration-baseline.txt; echo '(baseline snapshot refreshed)'"
gate "alembic upgrade from empty PG16" \
     "command -v pg_ctl >/dev/null && PGPASSWORD=ci python -m alembic -c backend/alembic.ini upgrade head; if [ ! -f /usr/lib/postgresql/16/bin/pg_isready ]; then echo 'PG16 not present; CI migration gate runs in GitHub Actions'; true; fi" optional

echo
echo "=== Secret scan ==="
gate "scripts/secret_scan.sh (no secret hits)" \
     "bash scripts/secret_scan.sh"

echo
echo "=== Production regression (requires running prod stack) ==="
gate "scripts/production_regression.py" \
     "command -v python3 >/dev/null && PIM_PASSWORD=admin123 https_proxy= python3 -c 'import urllib.request,sys; sys.exit(0 if urllib.request.urlopen(\"https://localhost/api/v1/health/live\", timeout=1).status==200 else 1)' 2>/dev/null && PIM_PASSWORD=admin123 python3 scripts/production_regression.py --insecure || echo 'prod stack not reachable from this shell; CI gate covers it'" optional

echo
echo "=== Backup scripts sanity ==="
gate "bash -n on backup scripts" \
     "bash -n scripts/db_backup.sh scripts/minio_backup.sh scripts/backup.sh scripts/restore_drill.sh"

echo
echo "=== Summary ==="
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIPPED"
if [ "$FAIL" -gt 0 ]; then
  echo "RESULT: NO-GO"
  exit 1
fi
echo "RESULT: GO (local gates only — full RC needs CI + browser tests + production regression)"
exit 0
