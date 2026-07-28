from __future__ import annotations

import json
from pathlib import Path

from app.knowledge.planner import RuleBasedPlanner
from app.knowledge.schemas import KnowledgeQueryRequest


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    evalset = root / 'eval' / 'p2' / 'evalset.jsonl'
    report_dir = root / 'eval' / 'reports'
    report_dir.mkdir(parents=True, exist_ok=True)
    planner = RuleBasedPlanner()
    total = 0
    blocked = 0
    for line in evalset.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not item.get('expected_reject'):
            continue
        total += 1
        plan = planner.plan(KnowledgeQueryRequest(message=item['query']))
        if plan.intent.value == 'unsupported':
            blocked += 1
    report = {
        'suite': 'p2-security',
        'total': total,
        'blocked': blocked,
        'block_rate': round(blocked / total, 4) if total else 0.0,
        'status': 'ok',
    }
    (report_dir / 'p2-security-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
