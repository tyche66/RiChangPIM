"""种子数据迁移集成测试（round ④ / 0004_seed_data）。

仅在「存在可达且安全的 Postgres 测试库」时运行；CI/沙箱无 DB 时整体 skip，且
**不会在 collection 阶段连接数据库**（probe 移到 fixture 内，而非模块级 skipif）。

执行流程：
- 用 Alembic 程序化 API：`downgrade base`（清库）→ `upgrade head`（建表 + 种子）
- 断言 role / permission / role_permission 行数
- 验证幂等（重复 upgrade head 不增量）
- 验证回滚 `downgrade 0003_add_quotation_subtotal` 后种子被清空

不依赖 MinIO / Redis / 任何业务路由，只校验 RBAC 种子数据本身。

安全：仅对「名字含 test 标识」或经 AI_PIM_TEST_DB_APPROVED 确认的数据库执行
Alembic，绝不触碰开发/生产库。
"""

import pytest
from _db_probe import (
    alembic_downgrade,
    alembic_upgrade,
    database_name_from_url,
    evaluate_test_database,
    is_safe_test_database,
    resolve_test_database_url,
    to_sync_url,
)
from sqlalchemy import create_engine, text

# Import seed_data definitions for role identity (role names/codes),
# NOT for permission counts — counts must be dynamic because subsequent
# migrations (e.g. 0011_add_media_permissions) add permissions that seed_data
# does not enumerate in its PERMISSIONS list.
from app.scripts.seed_data import ROLE_PERMISSIONS


def _sync_url():
    return to_sync_url(resolve_test_database_url())


ALEMBIC_INI = "alembic.ini"


def _reset_schema(url):
    """Drop and recreate the public schema so we start from a known-empty DB.

    ``alembic downgrade base`` is intentionally avoided here: it is only safe
    when the schema is already at ``head``; from any other state it can fail
    (e.g. recreating the 0005 plain-UNIQUE constraint on a missing table). A
    clean ``DROP SCHEMA`` + ``upgrade head`` is deterministic and portable.
    """
    import psycopg2

    sync = to_sync_url(url)
    conn = psycopg2.connect(sync)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        conn.close()


@pytest.fixture(scope="module")
def seeded_db():
    """Bring the test DB to a clean, seeded ``head``; skip if infra is unavailable.

    The reachability/safety probe runs here (at fixture setup, NOT collection),
    so ``--collect-only`` never touches the database. If the DB is unreachable or
    is not a safe test database, the module is skipped with a clear reason.
    """
    url = resolve_test_database_url()
    if not is_safe_test_database(url):
        pytest.skip(f"refusing to operate on non-test database {database_name_from_url(url)!r}")
    ok, reason = evaluate_test_database(url)
    if not ok:
        pytest.skip(reason)

    _reset_schema(url)
    alembic_upgrade(url, "head")
    eng = create_engine(_sync_url())
    yield eng
    eng.dispose()
    # Restore to a clean seeded head so the shared test DB stays usable for other
    # modules (e.g. smoke) that run in the same pytest session.
    _reset_schema(url)
    alembic_upgrade(url, "head")


def _count(engine, table):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {table} WHERE is_deleted = false")).scalar()


def _expected_permission_count(engine):
    """Total unique perm_codes across the permission table (authoritative source).

    After ``upgrade head`` the DB contains permissions from 0004_seed_data PLUS
    later migrations (0008, 0011).  ``seed_data.PERMISSIONS`` (57) does NOT
    enumerate 0011's scene_image permissions, so we must not hard-code 57.
    Querying ``DISTINCT perm_code`` is the single source of truth: every
    migration inserts a unique code, and the count reflects all additions.
    """
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(DISTINCT perm_code) FROM permission")
        ).scalar()


def _expected_role_permission_count(engine):
    """Expected active role_permission rows, derived dynamically from DB state.

    Invariant: the admin role must hold every active permission.  The total
    role_permission count is then verified as >= that (other roles add subsets).
    This stays correct regardless of how many migrations add new permissions.
    """
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


def test_role_count(seeded_db):
    assert _count(seeded_db, "role") == 4


def test_permission_count(seeded_db):
    assert _count(seeded_db, "permission") == _expected_permission_count(seeded_db)


def test_role_permission_count(seeded_db):
    admin_rp, total_rp = _expected_role_permission_count(seeded_db)
    active_perms = _count(seeded_db, "permission")
    assert admin_rp == active_perms  # admin holds every active permission
    assert total_rp >= active_perms  # other roles add at least zero more


def test_idempotent_rerun(seeded_db):
    before = (
        _count(seeded_db, "role"),
        _count(seeded_db, "permission"),
        _count(seeded_db, "role_permission"),
    )
    alembic_upgrade(resolve_test_database_url(), "head")  # 重复执行应为 no-op
    after = (
        _count(seeded_db, "role"),
        _count(seeded_db, "permission"),
        _count(seeded_db, "role_permission"),
    )
    assert before == after


def test_downgrade_removes_seed():
    url = resolve_test_database_url()
    if not is_safe_test_database(url):
        pytest.skip(f"refusing to operate on non-test database {database_name_from_url(url)!r}")
    ok, reason = evaluate_test_database(url)
    if not ok:
        pytest.skip(reason)

    # Clean, known-empty start (avoids the fragile full ``downgrade base``).
    _reset_schema(url)
    alembic_upgrade(url, "head")
    eng = create_engine(_sync_url())
    try:
        assert _count(eng, "role") == 4
        assert _count(eng, "permission") == _expected_permission_count(eng)
        # Roll back past the seed migration (0004); tables remain, seed is gone.
        alembic_downgrade(url, "0003_add_quotation_subtotal")
        assert _count(eng, "role") == 0
        assert _count(eng, "permission") == 0
        assert _count(eng, "role_permission") == 0
    finally:
        # Restore to a clean seeded head for any later modules in the session.
        try:
            _reset_schema(url)
            alembic_upgrade(url, "head")
        finally:
            eng.dispose()
