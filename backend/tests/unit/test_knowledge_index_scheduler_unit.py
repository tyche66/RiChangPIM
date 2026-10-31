"""夜间向量索引调度服务的纯单元测试（不连数据库）。

覆盖：时区与 01:00/02:25/02:30 窗口边界、跨午夜窗口、错误信息脱敏、
指数退避、管线标签。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.models.knowledge_index_admin import RUN_NOW_HARD_CAP, KnowledgeIndexSetting
from app.services.knowledge_index_scheduler import (
    backoff_seconds,
    compute_window,
    parse_hhmm,
    pipeline_tag,
    sanitize_text,
)


def _setting(**overrides) -> KnowledgeIndexSetting:
    values = dict(
        timezone="Asia/Shanghai",
        window_start="01:00",
        window_end="02:30",
        safety_cutoff_minutes=5,
    )
    values.update(overrides)
    return KnowledgeIndexSetting(**values)


def _utc(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


SH = ZoneInfo("Asia/Shanghai")


class TestWindowBoundaries:
    def test_before_window_start(self):
        # 北京时间 2026-03-15 00:59 → 窗口未开始，下次 01:00
        plan = compute_window(_setting(), _utc(2026, 3, 14, 16, 59))
        assert plan.active is False
        assert plan.start_utc == datetime(2026, 3, 14, 17, 0, tzinfo=UTC)
        assert plan.next_start_utc == plan.start_utc

    def test_window_start_0100_active(self):
        # 北京时间 01:00:00 → 窗口激活
        plan = compute_window(_setting(), _utc(2026, 3, 14, 17, 0))
        assert plan.active is True
        assert plan.end_utc == datetime(2026, 3, 14, 18, 30, tzinfo=UTC)

    def test_cutoff_at_0225(self):
        # 安全截止 = 02:30 - 5min = 02:25
        plan = compute_window(_setting(), _utc(2026, 3, 14, 18, 24))
        assert plan.active is True
        assert plan.cutoff_utc == datetime(2026, 3, 14, 18, 25, tzinfo=UTC)

    def test_after_cutoff_still_in_window(self):
        # 02:25 之后仍在窗口内（可处理 delete / 收尾），但 embedding 截止已过
        plan = compute_window(_setting(), _utc(2026, 3, 14, 18, 26))
        assert plan.active is True
        assert plan.cutoff_utc == datetime(2026, 3, 14, 18, 25, tzinfo=UTC)

    def test_window_end_0230_inactive_next_start_tomorrow(self):
        plan = compute_window(_setting(), _utc(2026, 3, 14, 18, 31))
        assert plan.active is False
        assert plan.next_start_utc == datetime(2026, 3, 15, 17, 0, tzinfo=UTC)

    def test_safety_cutoff_zero_means_cutoff_at_end(self):
        plan = compute_window(_setting(safety_cutoff_minutes=0), _utc(2026, 3, 14, 18, 29))
        assert plan.cutoff_utc == plan.end_utc

    def test_cross_midnight_window(self):
        # 23:30 - 01:30 跨午夜窗口
        setting = _setting(window_start="23:30", window_end="01:30")
        plan = compute_window(setting, _utc(2026, 3, 14, 16, 0))  # 北京 15 日 00:00
        assert plan.active is True
        assert plan.end_utc == datetime(2026, 3, 14, 17, 30, tzinfo=UTC)

    def test_timezone_fallback_for_shanghai(self):
        from app.services.knowledge_index_scheduler import resolve_tz

        tz = resolve_tz("Asia/Shanghai")
        dt = datetime(2026, 3, 14, 12, 0, tzinfo=UTC).astimezone(tz)
        assert dt.utcoffset() == timedelta(hours=8)

    def test_invalid_hhmm_rejected(self):
        with pytest.raises(ValueError):
            parse_hhmm("24:00")
        with pytest.raises(ValueError):
            parse_hhmm("01:60")
        with pytest.raises(ValueError):
            parse_hhmm("abc")


class TestSanitize:
    def test_masks_sk_style_keys(self):
        text = sanitize_text("request failed with key sk-ab12cd34ef56gh")
        assert "sk-ab12cd34ef56gh" not in text
        assert "***" in text

    def test_masks_bearer_tokens(self):
        text = sanitize_text("Unauthorized: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in text

    def test_masks_known_secret_values(self):
        text = sanitize_text("connect failed using SECRET-VALUE-123", secrets={"SECRET-VALUE-123"})
        assert "SECRET-VALUE-123" not in text
        assert "SECRET-VALUE-123" not in text

    def test_single_line_truncated(self):
        text = sanitize_text("line1\nline2\nline3" + "x" * 500)
        assert "\n" not in text
        assert len(text) <= 240

    def test_empty(self):
        assert sanitize_text(None) == ""


class TestBackoff:
    def test_exponential_growth(self):
        setting = _setting(backoff_base_seconds=60, backoff_max_seconds=1800)
        assert backoff_seconds(setting, 0) == 60
        assert backoff_seconds(setting, 1) == 120
        assert backoff_seconds(setting, 2) == 240

    def test_capped_at_max(self):
        setting = _setting(backoff_base_seconds=60, backoff_max_seconds=1800)
        assert backoff_seconds(setting, 10) == 1800


class TestPipelineTag:
    def test_tag_contains_model_and_version(self):
        tag = pipeline_tag("m-1", "v-9")
        assert "m-1" in tag and "v-9" in tag
        assert tag.startswith("product-card-v2")

    def test_run_now_hard_cap_constant(self):
        assert RUN_NOW_HARD_CAP == 200
