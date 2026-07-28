#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

cd "$ROOT/portal"
npx playwright install --with-deps chromium
npm run test:e2e
