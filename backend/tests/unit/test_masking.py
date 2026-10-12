"""Unit tests for PII masking functions (HLD §7).

Tests mask_phone, mask_wechat, mask_address with various inputs including
edge cases (empty, short, international formats).
"""

import pytest

from app.core.masking import mask_address, mask_phone, mask_wechat


class TestMaskPhone:
    """Phone number masking tests."""

    def test_mobile_11_digits(self):
        """Standard 11-digit mobile: keep first 3 + last 4."""
        assert mask_phone("13812341234") == "138****1234"

    def test_landline_with_dash(self):
        """Landline with dash: digits extracted, prefix kept."""
        assert mask_phone("0571-88889999") == "0571****9999"

    def test_short_number(self):
        """Less than 7 digits -> fully masked."""
        assert mask_phone("123") == "****"

    def test_empty_string(self):
        """Empty string -> fully masked."""
        assert mask_phone("") == "****"

    def test_none(self):
        """None -> fully masked."""
        assert mask_phone(None) == "****"

    def test_exactly_7_digits(self):
        """Exactly 7 digits: prefix_len=0, so **** + last 4."""
        assert mask_phone("1234567") == "****4567"

    def test_international_format(self):
        """International format with +86 prefix."""
        result = mask_phone("+86-138-1234-1234")
        # digits = "8613812341234" (13 digits), prefix=5, suffix=4
        assert result == "86138****1234"


class TestMaskWechat:
    """WeChat ID masking tests."""

    def test_normal_wechat(self):
        """Normal wechat ID: keep first 2 + ***."""
        assert mask_wechat("abcdefg") == "ab***"

    def test_two_chars(self):
        """Two characters -> fully masked as single *."""
        assert mask_wechat("ab") == "*"

    def test_single_char(self):
        """Single character -> fully masked."""
        assert mask_wechat("a") == "*"

    def test_empty_string(self):
        """Empty string -> fully masked."""
        assert mask_wechat("") == "*"

    def test_none(self):
        """None -> fully masked."""
        assert mask_wechat(None) == "*"


class TestMaskAddress:
    """Address masking tests."""

    def test_full_address(self):
        """Full address: keep up to city level + ***."""
        assert mask_address("浙江省杭州市余杭区文一西路969号") == "浙江省杭州市***"

    def test_city_only(self):
        """City name only -> *** (no 市 character)."""
        assert mask_address("北京市") == "***"

    def test_empty_string(self):
        """Empty string -> ***."""
        assert mask_address("") == "***"

    def test_none(self):
        """None -> ***."""
        assert mask_address(None) == "***"

    def test_province_no_city(self):
        """Province without city -> ***."""
        assert mask_address("浙江省") == "***"

    def test_city_with_district(self):
        """Address with city and district: keep through city."""
        assert mask_address("广东省深圳市南山区") == "广东省深圳市***"
