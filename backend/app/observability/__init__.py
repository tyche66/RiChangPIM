"""V1.2 observability package.

Zero-dependency Prometheus-text-format metrics + lightweight runtime state.
Importing this module MUST NOT pull any third-party packages (no prometheus_client)
to keep supply-chain risk surface minimal for V1.2.

Modules:
- ``metrics``: Prom-text 1.0 exposition format, thread-safe counters + histogram.
- ``runtime_state``: backup status, capacity thresholds, AI/OCR toggle snapshot.
"""

from __future__ import annotations

__all__: list[str] = []
