#!/bin/bash
cd /home/AI-PIM/RiChangPIM/backend || exit 9
show() { echo "=== $1 [$2]"; awk "NR>=$2-1 && NR<=$2+1 {printf '%d| %s\n', NR, \$0}" "$1"; }
show app/adapters/openai.py 388
show app/api/v1/files.py 95
show app/api/v1/files.py 150
show app/api/v1/files.py 506
show app/api/v1/knowledge.py 36
show app/api/v1/products.py 666
show app/api/v1/products.py 871
show app/api/v1/quotations.py 284
show app/api/v1/quotations.py 285
show app/api/v1/quotations.py 334
echo "=== quotations 400-412"; sed -n '400,412p' app/api/v1/quotations.py | cat -n | sed 's/^/  /'
echo "=== quotations 488-497"; sed -n '488,497p' app/api/v1/quotations.py | cat -n | sed 's/^/  /'
show app/api/v1/scene_images.py 220
show app/api/v1/shares.py 48
show app/knowledge/metrics.py 18
show app/knowledge/model_gateway.py 26
show app/knowledge/model_gateway.py 36
echo "=== model_gateway 48-60"; sed -n '48,60p' app/knowledge/model_gateway.py | cat -n | sed 's/^/  /'
show app/knowledge/policy.py 18
show app/knowledge/policy.py 22
show app/knowledge/pricing.py 8
echo "=== pricing 1-16"; sed -n '1,16p' app/knowledge/pricing.py | cat -n | sed 's/^/  /'
show app/knowledge/retrieval/exact.py 10
▷ echo skip
