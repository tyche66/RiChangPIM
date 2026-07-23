"""Unit tests for the manuals module's response envelope helper.

Regression: ``delete_manual`` previously called ``_envelope()`` with no
arguments, but the helper's first parameter ``data`` had no default, so the
endpoint raised ``TypeError`` *after* the DB commit. The soft-delete landed
in the database, but the response became 500, leaving the user thinking the
delete failed.
"""

from app.api.v1.manuals import _envelope


def test_envelope_no_args():
    """_envelope() must be callable with no arguments (delete endpoints rely on this)."""
    result = _envelope()
    assert result == {"code": 200, "data": None, "msg": "success"}


def test_envelope_explicit_none_data():
    result = _envelope(None)
    assert result == {"code": 200, "data": None, "msg": "success"}


def test_envelope_with_payload():
    result = _envelope({"indexed": 5})
    assert result == {"code": 200, "data": {"indexed": 5}, "msg": "success"}


def test_envelope_overrides_code_and_msg():
    result = _envelope(code=500, msg="boom")
    assert result == {"code": 500, "data": None, "msg": "boom"}
