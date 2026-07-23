"""Zero-dependency Prometheus 1.0 text-exposition metrics.

Design goals (per docs/v1.2-plan.md §5.2):
- No third-party packages: keeps supply-chain / vulnerability surface minimal.
- Thread-safe: FastAPI + uvicorn workers run in async threads; use `threading.Lock`.
  (Python `asyncio` is single-threaded per worker, but `to_thread` executors can
  touch this state, so a lock is cheap and correct.)
- Histograms follow Prometheus standard bucket convention:
  ``<name>_bucket{le="..."}`` cumulative buckets + ``_count`` + ``_sum``.
- All public functions accept (and validate) label cardinality at write time to
  bound memory growth (route/method/status are small bounded sets).
- Metric names are namespaced ``pim_*``.

This module is intentionally minimal and focused on what the SRE brief needs:
per-route HTTP latency/error counters, DB pool usage, AI/OCR outcomes,
backup timestamps, and volume capacity gauges.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Iterable

_CONTENT_TYPE = "text/plain; version=1.0.0; charset=utf-8"

# Standard Prometheus histogram buckets for HTTP request durations (seconds).
_DEFAULT_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

_POS_INF = float("inf")


class _Counter:
    __slots__ = ("name", "help", "values", "label_names", "lock")

    def __init__(self, name: str, help: str, label_names: Iterable[str]):
        self.name = name
        self.help = help
        self.label_names = tuple(label_names)
        self.values: dict[tuple[str, ...], float] = defaultdict(float)
        self.lock = threading.Lock()

    def inc(self, labels: dict[str, str], amount: float = 1.0) -> None:
        key = tuple(labels.get(n, "") for n in self.label_names)
        with self.lock:
            self.values[key] += amount

    def render(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.help}",
            f"# TYPE {self.name} counter",
        ]
        with self.lock:
            items = list(self.values.items())
        if not items:
            return lines
        for key, val in items:
            label_str = ",".join(
                f'{n}="{_escape_label(k)}"'
                for n, k in zip(self.label_names, key, strict=True)
            )
            lines.append(f'{self.name}{{{label_str}}} {val:.17g}')
        return lines


class _Gauge:
    __slots__ = ("name", "help", "values", "label_names", "lock")

    def __init__(self, name: str, help: str, label_names: Iterable[str]):
        self.name = name
        self.help = help
        self.label_names = tuple(label_names)
        self.values: dict[tuple[str, ...], float] = {}
        self.lock = threading.Lock()

    def set(self, labels: dict[str, str], value: float) -> None:
        key = tuple(labels.get(n, "") for n in self.label_names)
        with self.lock:
            self.values[key] = float(value)

    def render(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.help}",
            f"# TYPE {self.name} gauge",
        ]
        with self.lock:
            items = list(self.values.items())
        if not items:
            return lines
        for key, val in items:
            if self.label_names:
                label_str = ",".join(
                    f'{n}="{_escape_label(k)}"'
                    for n, k in zip(self.label_names, key, strict=True)
                )
                lines.append(f"{self.name}{{{label_str}}} {val:.17g}")
            else:
                lines.append(f"{self.name} {val:.17g}")
        return lines


class _Histogram:
    __slots__ = ("name", "help", "buckets", "counts", "sums", "lock")

    def __init__(self, name: str, help: str, buckets: Iterable[float] = _DEFAULT_BUCKETS):
        self.name = name
        self.help = help
        self.buckets: tuple[float, ...] = tuple(buckets) + (_POS_INF,)
        self.counts: dict[float, int] = {ub: 0 for ub in self.buckets}
        self.sums: float = 0.0
        self.lock = threading.Lock()

    def observe(self, value: float) -> None:
        v = float(value)
        with self.lock:
            self.sums += v
            for ub in self.buckets:
                if v <= ub:
                    self.counts[ub] += 1

    def render(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.help}",
            f"# TYPE {self.name} histogram",
        ]
        with self.lock:
            snapshot = dict(self.counts)
            sum_val = self.sums
        total = 0
        for ub in self.buckets:
            total = snapshot.get(ub, 0)
            le = "+Inf" if ub == _POS_INF else _format_le(ub)
            lines.append(f'{self.name}_bucket{{le="{le}"}} {total}')
        lines.append(f"{self.name}_count {total}")
        lines.append(f"{self.name}_sum {sum_val:.17g}")
        return lines


def _format_le(ub: float) -> str:
    # Prometheus expects e.g. "0.01", "0.5"; avoid "-0" and trailing zeros for cleanliness.
    if ub == int(ub):
        return f"{int(ub)}"
    return f"{ub:g}"


def _escape_label(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


# ---------------------------------------------------------------------------
# Registry (module-level singletons)
# ---------------------------------------------------------------------------
_http_requests_total = _Counter(
    "pim_http_requests_total",
    "Total HTTP requests by method, route template, and HTTP status code.",
    ("method", "route", "status"),
)
_http_request_duration_seconds = _Histogram(
    "pim_http_request_duration_seconds",
    "HTTP request duration in seconds, measured by the audit middleware.",
)
_db_pool_in_use = _Gauge(
    "pim_db_pool_in_use",
    "Number of SQLAlchemy pool connections currently checked out.",
    (),
)
_db_pool_available = _Gauge(
    "pim_db_pool_available",
    "Number of SQLAlchemy pool connections available (size - in_use).",
    (),
)
_ai_requests_total = _Counter(
    "pim_ai_requests_total",
    "AI adapter requests by adapter name and outcome.",
    ("adapter", "outcome"),
)
_ocr_requests_total = _Counter(
    "pim_ocr_requests_total",
    "OCR adapter requests by adapter name and outcome.",
    ("adapter", "outcome"),
)
_backup_last_success_timestamp = _Gauge(
    "pim_backup_last_success_timestamp",
    "Unix timestamp of the most recent successful backup batch.",
    ("batch",),
)
_backup_last_failure_timestamp = _Gauge(
    "pim_backup_last_failure_timestamp",
    "Unix timestamp of the most recent failed backup batch.",
    ("batch",),
)
_backup_status = _Gauge(
    "pim_backup_status",
    "Backup batch status (1=ok, 0=incomplete/failed).",
    ("batch",),
)
_volume_free_bytes = _Gauge(
    "pim_volume_free_bytes",
    "Free bytes on a filesystem backing a PIM volume or backup directory.",
    ("target",),
)
_volume_threshold_bytes = _Gauge(
    "pim_volume_threshold_bytes",
    "Configured free-bytes threshold below which capacity alert fires.",
    ("target",),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def observe_http_request(method: str, route: str, status: int, duration_seconds: float) -> None:
    """Record one HTTP request (called by AuditMiddleware)."""
    _http_requests_total.inc({"method": method, "route": route, "status": str(status)})
    _http_request_duration_seconds.observe(duration_seconds)


def set_db_pool(in_use: int, available: int) -> None:
    _db_pool_in_use.set({}, float(in_use))
    _db_pool_available.set({}, float(available))


def inc_ai_request(adapter: str, outcome: str) -> None:
    """``outcome`` ∈ {success, fail, timeout, ratelimit}."""
    _ai_requests_total.inc({"adapter": adapter, "outcome": outcome})


def inc_ocr_request(adapter: str, outcome: str) -> None:
    """``outcome`` ∈ {success, fail, timeout}."""
    _ocr_requests_total.inc({"adapter": adapter, "outcome": outcome})


def set_backup_status(batch: str, success: bool, timestamp: float | None = None) -> None:
    ts = timestamp if timestamp is not None else time.time()
    if success:
        _backup_last_success_timestamp.set({"batch": batch}, ts)
        _backup_status.set({"batch": batch}, 1.0)
    else:
        _backup_last_failure_timestamp.set({"batch": batch}, ts)
        _backup_status.set({"batch": batch}, 0.0)


def set_volume_free(target: str, free_bytes: int, threshold_bytes: int) -> None:
    _volume_free_bytes.set({"target": target}, float(free_bytes))
    _volume_threshold_bytes.set({"target": target}, float(threshold_bytes))


def render_text() -> str:
    """Full Prometheus exposition text payload (version 1.0)."""
    parts: list[str] = []
    parts.extend(_http_requests_total.render())
    parts.extend(_http_request_duration_seconds.render())
    parts.extend(_db_pool_in_use.render())
    parts.extend(_db_pool_available.render())
    parts.extend(_ai_requests_total.render())
    parts.extend(_ocr_requests_total.render())
    parts.extend(_backup_last_success_timestamp.render())
    parts.extend(_backup_last_failure_timestamp.render())
    parts.extend(_backup_status.render())
    parts.extend(_volume_free_bytes.render())
    parts.extend(_volume_threshold_bytes.render())
    parts.append("")
    return "\n".join(parts)


CONTENT_TYPE = _CONTENT_TYPE
__all__ = [
    "CONTENT_TYPE",
    "inc_ai_request",
    "inc_ocr_request",
    "observe_http_request",
    "render_text",
    "reset",
    "set_backup_status",
    "set_db_pool",
    "set_volume_free",
]


def reset() -> None:
    """Clear all metrics state. Intended for test isolation only.

    Resets every module-level counter/gauge/histogram singleton so that
    subsequent ``render_text()`` calls start from an empty baseline.
    """
    _http_requests_total.values.clear()
    _http_request_duration_seconds.counts = {ub: 0 for ub in _http_request_duration_seconds.buckets}
    _http_request_duration_seconds.sums = 0.0
    _db_pool_in_use.values.clear()
    _db_pool_available.values.clear()
    _ai_requests_total.values.clear()
    _ocr_requests_total.values.clear()
    _backup_last_success_timestamp.values.clear()
    _backup_last_failure_timestamp.values.clear()
    _backup_status.values.clear()
    _volume_free_bytes.values.clear()
    _volume_threshold_bytes.values.clear()
