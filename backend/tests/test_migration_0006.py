"""Migration schema tests for 0006_add_manual_indexing.

Verifies that after ``alembic upgrade head``:
- ``product_manual`` has ``index_status``, ``index_error``, ``content_hash``,
  ``last_indexed_at`` columns and the ``check_product_manual_index_status``
  CHECK constraint.
- ``product_manual_chunk`` has ``chunk_hash`` and the
  ``uq_chunk_manual_index`` unique constraint.
- ``ai_conversation`` has ``model``, ``token_usage``, ``status``,
  ``request_summary``, ``response_summary`` columns.
"""

import pytest
from _db_probe import (
    alembic_upgrade,
    evaluate_test_database,
    is_safe_test_database,
    resolve_test_database_url,
    to_sync_url,
)
from sqlalchemy import create_engine, text


def _safe_url():
    url = resolve_test_database_url()
    if not is_safe_test_database(url):
        pytest.skip("refusing to operate on non-test database")
    ok, reason = evaluate_test_database(url)
    if not ok:
        pytest.skip(reason)
    return url


def _reset_schema(url):
    import psycopg2

    conn = psycopg2.connect(to_sync_url(url))
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        conn.close()


def _column_exists(engine, table, column):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:tbl "
                "AND column_name=:col"
            ),
            {"tbl": table, "col": column},
        ).first()
    return row is not None


def _constraint_exists(engine, table, constraint_name, constraint_type="c"):
    """constraint_type: 'c'=check, 'u'=unique, 'p'=primary key, 'f'=foreign key."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid "
                "WHERE t.relname=:tbl AND c.conname=:cname AND c.contype=:ctype"
            ),
            {"tbl": table, "cname": constraint_name, "ctype": constraint_type},
        ).first()
    return row is not None


def _unique_constraint_exists(engine, table, constraint_name):
    return _constraint_exists(engine, table, constraint_name, "u")


# ---------------------------------------------------------------------------
# Module-level fixtures.  Using scope="module" avoids the class-scoped instance
# fixture pattern that triggers PytestRemovedIn10Warning in Python 3.14.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine_pm():
    """Single engine for product_manual column / constraint checks."""
    url = _safe_url()
    _reset_schema(url)
    alembic_upgrade(url, "head")
    return create_engine(to_sync_url(url))


@pytest.fixture(scope="module")
def engine_chunk():
    url = _safe_url()
    _reset_schema(url)
    alembic_upgrade(url, "head")
    return create_engine(to_sync_url(url))


@pytest.fixture(scope="module")
def engine_conv():
    url = _safe_url()
    _reset_schema(url)
    alembic_upgrade(url, "head")
    return create_engine(to_sync_url(url))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_index_status_column(engine_pm):
    assert _column_exists(engine_pm, "product_manual", "index_status")


def test_index_error_column(engine_pm):
    assert _column_exists(engine_pm, "product_manual", "index_error")


def test_content_hash_column(engine_pm):
    assert _column_exists(engine_pm, "product_manual", "content_hash")


def test_last_indexed_at_column(engine_pm):
    assert _column_exists(engine_pm, "product_manual", "last_indexed_at")


def test_check_constraint_index_status(engine_pm):
    assert _constraint_exists(
        engine_pm, "product_manual", "check_product_manual_index_status", "c"
    )


def test_chunk_hash_column(engine_chunk):
    assert _column_exists(engine_chunk, "product_manual_chunk", "chunk_hash")


def test_unique_constraint_manual_index(engine_chunk):
    assert _unique_constraint_exists(
        engine_chunk, "product_manual_chunk", "uq_chunk_manual_index"
    )


def test_model_column(engine_conv):
    assert _column_exists(engine_conv, "ai_conversation", "model")


def test_token_usage_column(engine_conv):
    assert _column_exists(engine_conv, "ai_conversation", "token_usage")


def test_status_column(engine_conv):
    assert _column_exists(engine_conv, "ai_conversation", "status")


def test_request_summary_column(engine_conv):
    assert _column_exists(engine_conv, "ai_conversation", "request_summary")


def test_response_summary_column(engine_conv):
    assert _column_exists(engine_conv, "ai_conversation", "response_summary")