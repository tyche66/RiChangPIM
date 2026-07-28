from __future__ import annotations

import json
from pathlib import Path

from app.knowledge.planner import RuleBasedPlanner
from app.knowledge.schemas import KnowledgeQueryRequest


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    evalset = root / 'eval' / 'p1' / 'evalset.jsonl'
    report_dir = root / 'eval' / 'reports'
    report_dir.mkdir(parents=True, exist_ok=True)
    planner = RuleBasedPlanner()
    total = 0
    rejected = 0
    for line in evalset.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        total += 1
        plan = planner.plan(KnowledgeQueryRequest(message=item['query']))
        if item.get('expected_reject') and plan.intent.value == 'unsupported':
            rejected += 1
    report = {
        'suite': 'p1',
        'total': total,
        'rejected_expected_cases': rejected,
        'status': 'ok',
    }
    (report_dir / 'p1-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
