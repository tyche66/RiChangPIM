#!/bin/bash
cd /home/AI-PIM/RiChangPIM/backend || exit 9
for f in app/knowledge/tools/product.py app/knowledge/tools/quality.py app/knowledge/sessions.py app/api/v1/quotations.py app/observability/metrics.py; do
  awk 'length > 100 {printf "L%d(%d): %s\n", NR, length, substr($0,1,50)}' "$f"
done
