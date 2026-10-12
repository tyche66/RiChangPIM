#!/usr/bin/env bash
# Purge old operation logs
# Regular logs: 180 days
# PII/Export logs: 730 days
# Per HLD §15
set -euo pipefail

DATABASE_URL="${DATABASE_URL:?DATABASE_URL is required}"

psql "$DATABASE_URL" -c "
DELETE FROM operation_log WHERE create_time < NOW() - INTERVAL '180 days' AND action NOT IN ('customer_pii_view', 'customer_export', 'content_export');
DELETE FROM operation_log WHERE create_time < NOW() - INTERVAL '730 days' AND action IN ('customer_pii_view', 'customer_export', 'content_export');
"

echo "Operation log purge completed."
