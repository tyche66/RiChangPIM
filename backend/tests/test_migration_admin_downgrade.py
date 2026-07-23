"""0004 admin downgrade 数据安全集成测试（Task 3）。

验证：Alembic downgrade 不得删除升级前已存在的 admin 用户。

设计：本迁移创建的管理员使用确定性 UUID（alembic/versions/0004_seed_data.py 的
ADMIN_MIGRATION_ID），downgrade 仅删除该固定 id 的用户；升级前已存在的 admin
（随机 id）不会被波及。
"""

from uuid import uuid4

import pytest
from _db_probe import (
    alembic_downgrade,
    alembic_upgrade,
    evaluate_test_database,
    is_safe_test_database,
    resolve_test_database_url,
    to_sync_url,
)
from sqlalchemy import create_engine, text

# Dynamic seed count: computed from DB state (DISTINCT perm_code) so it stays
# correct when migrations add/remove permissions (e.g. 0011_add_media_permissions).
# The static PERMISSIONS / ROLE_PERMISSIONS constants in seed_data.py only
# describe the 0004 baseline, NOT the full ``head`` state.
# No import needed — counts come from the database itself.

EXPECTED_PERMISSION_COUNT = None  # signals "use DB query"


def _reset_schema(url):
    import psycopg2

    conn = psycopg2.connect(to_sync_url(url))
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        conn.close()


def _safe_url():
    url = resolve_test_database_url()
    if not is_safe_test_database(url):
        pytest.skip("refusing to operate on non-test database")
    ok, reason = evaluate_test_database(url)
    if not ok:
        pytest.skip(reason)
    return url


def _count(engine, table):
    with engine.connect() as conn:
        return conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE is_deleted = false")
        ).scalar()


def _expected_permission_count(engine):
    """Dynamic: count of unique perm_codes in the permission table."""
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(DISTINCT perm_code) FROM permission")
        ).scalar()


def _expected_role_permission_count(engine):
    """Dynamic: (admin_rp, total_rp) for role_permission verification."""
    with engine.connect() as conn:
        admin_rp = conn.execute(
            text(
                "SELECT count(*) FROM role_permission rp "
                "JOIN role r ON r.id = rp.role_id "
                "WHERE r.role_code = 'admin' AND rp.is_deleted = false"
            )
        ).scalar()
        total_rp = conn.execute(
            text("SELECT count(*) FROM role_permission WHERE is_deleted = false")
        ).scalar()
        return admin_rp, total_rp


def _admin_count(engine):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM \"user\" WHERE username = 'admin' AND is_deleted = false")
        ).scalar()


def _insert_preexisting_admin(engine):
    """在 0004 执行前，模拟业务库已存在 admin 用户（随机 id）。"""
    with engine.begin() as conn:
        role_id = str(uuid4())
        conn.execute(
            text(
                "INSERT INTO role (id, role_name, role_code, description, "
                "create_time, update_time, is_deleted) "
                "VALUES (:rid, '系统管理员', 'admin', 'pre', now(), now(), false)"
            ),
            {"rid": role_id},
        )
        user_id = str(uuid4())
        conn.execute(
            text(
                'INSERT INTO "user" (id, username, password_hash, role_id, status, '
                "create_time, update_time, is_deleted) "
                "VALUES (:uid, 'admin', 'x', :rid, 'active', now(), now(), false)"
            ),
            {"uid": user_id, "rid": role_id},
        )
        return user_id


def test_migration_owned_admin_deleted_on_downgrade():
    url = _safe_url()
    _reset_schema(url)
    alembic_upgrade(url, "head")
    eng = create_engine(to_sync_url(url))
    try:
        assert _admin_count(eng) == 1  # 本迁移创建的 admin
        assert _count(eng, "role") == 4
        if EXPECTED_PERMISSION_COUNT is None:
            assert _count(eng, "permission") == _expected_permission_count(eng)
        else:
            assert _count(eng, "permission") == EXPECTED_PERMISSION_COUNT
        admin_rp, total_rp = _expected_role_permission_count(eng)
        assert admin_rp == _count(eng, "permission")
        assert total_rp >= admin_rp
        alembic_downgrade(url, "0003_add_quotation_subtotal")
        assert _admin_count(eng) == 0  # migration-owned admin 被删除
        assert _count(eng, "role") == 0
        assert _count(eng, "permission") == 0
        assert _count(eng, "role_permission") == 0
    finally:
        _reset_schema(url)


def test_preexisting_admin_preserved_on_downgrade():
    url = _safe_url()
    _reset_schema(url)
    # 升到 0003（不含 admin 种子），再预置一个 admin，然后升到 head。
    alembic_upgrade(url, "0003_add_quotation_subtotal")
    eng = create_engine(to_sync_url(url))
    _insert_preexisting_admin(eng)
    alembic_upgrade(url, "head")
    try:
        # 升级前已存在 admin -> 本迁移 NOT EXISTS 守卫不重复插入。
        assert _admin_count(eng) == 1
        assert _count(eng, "role") == 4
        assert _count(eng, "permission") == _expected_permission_count(eng)
        admin_rp, total_rp = _expected_role_permission_count(eng)
        assert admin_rp == _count(eng, "permission")
        assert total_rp >= admin_rp
        alembic_downgrade(url, "0003_add_quotation_subtotal")
        # 升级前已有 admin 必须保留（其 id 与迁移确定性 id 不同）。
        assert _admin_count(eng) == 1
    finally:
        _reset_schema(url)


def test_downgrade_then_upgrade_recreates_admin():
    url = _safe_url()
    _reset_schema(url)
    alembic_upgrade(url, "head")
    eng = create_engine(to_sync_url(url))
    try:
        alembic_downgrade(url, "0003_add_quotation_subtotal")
        assert _admin_count(eng) == 0
        alembic_upgrade(url, "head")
        assert _admin_count(eng) == 1
        assert _count(eng, "role") == 4
        assert _count(eng, "permission") == _expected_permission_count(eng)
        admin_rp, total_rp = _expected_role_permission_count(eng)
        assert admin_rp == _count(eng, "permission")
        assert total_rp >= admin_rp
    finally:
        _reset_schema(url)


def test_idempotent_upgrade_does_not_duplicate_admin():
    url = _safe_url()
    _reset_schema(url)
    alembic_upgrade(url, "head")
    eng = create_engine(to_sync_url(url))
    try:
        assert _admin_count(eng) == 1
        alembic_upgrade(url, "head")  # 重复 upgrade 应为 no-op
        assert _admin_count(eng) == 1
    finally:
        _reset_schema(url)
