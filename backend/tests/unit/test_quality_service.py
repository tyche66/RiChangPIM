"""V1.2 pilot data quality service unit tests (pure, no DB)."""

from __future__ import annotations

from app.services import quality


def test_quality_flag_validator_accepts_known_flags():
    assert quality.is_valid_quality_flag(None) is True
    for flag in (
        "no_price",
        "no_image",
        "no_manual",
        "no_spec",
        "source_incomplete",
        "ocr_failed",
        "long_pending",
    ):
        assert quality.is_valid_quality_flag(flag) is True


def test_quality_flag_validator_rejects_unknown_flags():
    for bad in ("", "????", "no_picture_secret", "anything"):
        assert quality.is_valid_quality_flag(bad) is False


def test_placeholder_price_label_is_human_not_99999():
    # Per V1.2 §5.4 business red line: UI / export must NEVER show faux price.
    assert quality.PLACEHOLDER_PRICE_LABEL == "待核价"
    assert quality.PLACEHOLDER_PRICE_LABEL != str(quality._PLACEHOLDER_PRICE)
