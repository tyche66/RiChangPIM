#!/bin/bash
cd /home/AI-PIM/RiChangPIM/backend || exit 9
echo "== product.py: compare/inner/_CARD_FACT_FIELDS =="
grep -n '_CARD_FACT_FIELDS = (' -A6 app/knowledge/tools/product.py | head -9
grep -n 'class ProductCompareTool' -A22 app/knowledge/tools/product.py | grep -n 'run\|inner\|ProductGetMany'
echo "== quotations L155-165 =="
sed -n '155,165p' app/api/v1/quotations.py
echo "== product L275-280 =="
sed -n '275,280p' app/knowledge/tools/product.py
