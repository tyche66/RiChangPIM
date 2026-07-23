"""V1.2 observability metrics unit tests.

These tests are PURE UNIT — they do NOT import app.main or any DB code.
They verify the Prometheus-text rendering of counters/gauges/histograms and
the public API bookkeeping functions.
"""

from __future__ import annotations

import re

import pytest

from app.observability import metrics


@pytest.fixture(autouse=True)
def _clean_metrics():
    """Reset all metrics state before each test for isolation."""
    metrics.reset()
    yield
    metrics.reset()


def test_counter_inc_renders_with_labels():
    metrics.observe_http_request("GET", "/api/v1/products", 200, 0.123)
    text = metrics.render_text()
    assert "# HELP pim_http_requests_total" in text
    assert "# TYPE pim_http_requests_total counter" in text
    assert re.search(
        r'pim_http_requests_total\{method="GET",route="/api/v1/products",status="200"\} 1',
        text,
    )


def test_histogram_renders_buckets_and_count_sum():
    metrics.observe_http_request("POST", "/api/v1/products", 201, 0.05)
    text = metrics.render_text()
    assert "# TYPE pim_http_request_duration_seconds histogram" in text
    # Cumulative bucket lines must be present (+Inf must appear).
    assert "pim_http_request_duration_seconds_bucket{le=\"+Inf\"}" in text
    assert "pim_http_request_duration_seconds_count" in text
    assert "pim_http_request_duration_seconds_sum" in text


def test_set_db_pool_gauge_renders_in_use_and_available():
    metrics.set_db_pool(3, 7)
    text = metrics.render_text()
    assert "# TYPE pim_db_pool_in_use gauge" in text
    assert "pim_db_pool_in_use 3" in text
    assert "pim_db_pool_available 7" in text


def test_ai_ocr_counters_accept_outcomes():
    metrics.inc_ai_request("openai", "success")
    metrics.inc_ai_request("openai", "ratelimit")
    metrics.inc_ocr_request("dummy", "fail")
    text = metrics.render_text()
    assert "pim_ai_requests_total" in text
    assert "pim_ocr_requests_total" in text
    assert 'outcome="ratelimit"' in text
    assert 'outcome="fail"' in text


def test_backup_status_gauge_distinct_success_failure_buckets():
    metrics.set_backup_status("batch-2026-07-20-001", success=True, timestamp=1_700_000_000)
    metrics.set_backup_status("batch-2026-07-21-002", success=False, timestamp=1_700_086_400)
    text = metrics.render_text()
    assert "# TYPE pim_backup_status gauge" in text
    assert 'batch="batch-2026-07-20-001"' in text and "pim_backup_status{batch=\"batch-2026-07-20-001\"} 1" in text


def test_volume_gauge_renders_free_and_threshold():
    metrics.set_volume_free("backups", 1_000_000_000, 5 * 1024 ** 3)
    text = metrics.render_text()
    assert "# TYPE pim_volume_free_bytes gauge" in text
    assert "# TYPE pim_volume_threshold_bytes gauge" in text
    assert 'target="backups"' in text


def test_render_text_starts_with_help_line():
    text = metrics.render_text()
    # First non-empty line is always a HELP line.
    first = next(line for line in text.splitlines() if line)
    assert first.startswith("# HELP")


def test_label_escaping_disallows_quote_and_backslash_injection():
    # Directly exercise the private render path by registering a custom counter
    # whose label value contains a double-quote and a backslash.
    fake = metrics._Counter("pim_test_escape", "unit-only", ("k",))
    fake.inc({"k": 'a"b\\c'})
    rendered = fake.render()
    # The escaped label value must be a single token — no raw unescaped quotes
    # that would split the Prometheus line.
    line = [ln for ln in rendered if "pim_test_escape{" in ln][0]
    assert 'k="a\\"b\\\\c"' in line
