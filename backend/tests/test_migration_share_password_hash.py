"""0038 migration: existing plaintext share passwords become bcrypt hashes."""

from uuid import uuid4

import bcrypt
import pytest
from _db_probe import (
    alembic_upgrade,
    evaluate_test_database,
    is_safe_test_database,
    resolve_test_database_url,
    to_sync_url,
)
from sqlalchemy import create_engine, text


def _safe_url() -> str:
    url = resolve_test_database_url()
    if not is_safe_test_database(url):
        pytest.skip("refusing to operate on non-test database")
    ok, reason = evaluate_test_database(url)
    if not ok:
        pytest.skip(reason)
    return url


def _reset_schema(url: str) -> None:
    import psycopg2

    conn = psycopg2.connect(to_sync_url(url))
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        conn.close()


def test_0038_hashes_existing_share_password_and_keeps_it_usable():
    url = _safe_url()
    _reset_schema(url)
    alembic_upgrade(url, "0037_knowledge_index_scheduler")
    eng = create_engine(to_sync_url(url))
    share_id = uuid4()
    token_id = uuid4()
    try:
        with eng.begin() as conn:
            creator_id = conn.execute(
                text("SELECT id FROM \"user\" WHERE username = 'admin'")
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO share "
                    "(id, share_type, target_id, creator_id, status, create_time, update_time, is_deleted) "
                    "VALUES (:id, 'proposal', :target, :creator, 'active', now(), now(), false)"
                ),
                {"id": share_id, "target": uuid4(), "creator": creator_id},
            )
            conn.execute(
                text(
                    "INSERT INTO share_token "
                    "(id, share_id, token, password, status, current_access_count, "
                    " create_time, update_time, is_deleted) "
                    "VALUES (:id, :share_id, :token, :password, 'active', 0, now(), now(), false)"
                ),
                {
                    "id": token_id,
                    "share_id": share_id,
                    "token": f"legacy_{uuid4().hex}",
                    "password": "legacy-secret",
                },
            )

        alembic_upgrade(url, "head")
        with eng.connect() as conn:
            row = conn.execute(
                text("SELECT password, password_hash FROM share_token WHERE id = :id"),
                {"id": token_id},
            ).first()
        assert row is not None
        assert row.password.startswith("$2")
        assert row.password_hash.startswith("$2")
        assert row.password != "legacy-secret"
        assert row.password_hash != "legacy-secret"
        assert bcrypt.checkpw(b"legacy-secret", row.password_hash.encode("ascii"))
    finally:
        eng.dispose()
        _reset_schema(url)
