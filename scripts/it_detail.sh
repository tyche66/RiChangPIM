#!/bin/bash
cd /home/AI-PIM/RiChangPIM/frontend || exit 9
grep -n -A3 "test.skip\\|skip(" tests/e2e/auth.spec.ts tests/e2e/ai-features.spec.ts 2>/dev/null | head -14
