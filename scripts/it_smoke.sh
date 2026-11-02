#!/bin/bash
cd /home/AI-PIM/RiChangPIM/backend || exit 9
export TEST_DATABASE_URL='postgresql+asyncpg://pim:pim_password@localhost:5432/ai_pim_test'
/tmp/pimtestenv/bin/python -m pytest tests/test_seed_data.py tests/test_permission_contract.py tests/test_migration_schema.py -q -p no:cacheprovider 2>&1 | tail -8
echo "IT_SMOKE_EXIT=$?"
