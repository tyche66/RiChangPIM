from __future__ import annotations

import json
import re
from pathlib import Path


PRODUCT_NO_RE = re.compile(r'\b[A-Za-z]{2}-[A-Za-z0-9]{4,}\b|\bSN-[A-Z0-9]{4,}\b')


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    evalset = root / 'eval' / 'p2' / 'evalset.jsonl'
    report_dir = root / 'eval' / 'reports'
    report_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    exact_hits = 0
    for line in evalset.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        total += 1
        expected = set(item.get('expected_product_nos') or [])
        found = set(PRODUCT_NO_RE.findall(item['query']))
        if expected <= found:
            exact_hits += 1
    report = {
        'suite': 'p2-rag',
        'total': total,
        'product_entity_precision': round(exact_hits / total, 4) if total else 0.0,
        'status': 'ok',
    }
    (report_dir / 'p2-rag-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
