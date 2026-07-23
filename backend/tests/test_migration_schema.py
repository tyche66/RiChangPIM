"""迁移 schema 一致性测试（Task 2 teardown 状态 + Task 7 partial unique）。

仅在「存在可达且安全的 Postgres 测试库」时运行；CI/沙箱无 DB 时整体 skip。

覆盖：
- Task 2：teardown 后（DROP SCHEMA public CASCADE + CREATE SCHEMA）库处于一致状态，
  随后 ``alembic upgrade head`` 可完整恢复全部表；
- Task 7：全新库与「已执行旧 0001（含普通 UNIQUE）」的旧库，最终 schema 一致
  （无普通 UNIQUE、仅保留 partial UNIQUE）；并证明 0005 downgrade 在存在软删除
  重复数据时并非安全（数据导致的 downgrade 失败）。
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

EXPECTED_TABLES = {
    "role",
    "permission",
    "role_permission",
    "user",
    "category",
    "brand",
    "supplier",
    "tag",
    "attachment",
    "product",
    "product_tag",
    "product_image",
    "product_manual",
    "proposal",
    "proposal_item",
    "quotation",
    "quotation_item",
    "share",
    "share_token",
    "visitor",
    "share_log",
    "operation_log",
    "ai_conversation",
}


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


def _table_names(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        ).fetchall()
    return {r[0] for r in rows}


def _has_alembic_version(engine):
    with engine.connect() as conn:
        return (
            conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name='alembic_version'"
                )
            ).first()
            is not None
        )


def _has_regular_unique(engine, table, constraint):
    with engine.connect() as conn:
        return (
            conn.execute(
                text(
                    "SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid "
                    "WHERE t.relname=:tbl AND c.conname=:cname"
                ),
                {"tbl": table, "cname": constraint},
            ).first()
            is not None
        )


def _has_partial_unique_index(engine, table, index):
    with engine.connect() as conn:
        return (
            conn.execute(
                text(
                    "SELECT 1 FROM pg_class t JOIN pg_index ix ON ix.indrelid=t.oid "
                    "JOIN pg_class i ON i.oid=ix.indexrelid "
                    "WHERE t.relname=:tbl AND i.relname=:idx AND ix.indisunique"
                ),
                {"tbl": table, "idx": index},
            ).first()
            is not None
        )


def test_fresh_db_upgrade_head_has_consistent_schema():
    url = _safe_url()
    _reset_schema(url)
    alembic_upgrade(url, "head")
    eng = create_engine(to_sync_url(url))
    try:
        missing = EXPECTED_TABLES - _table_names(eng)
        assert not missing, f"missing tables: {missing}"
        # 无普通 UNIQUE（软删除语义）。
        assert not _has_regular_unique(eng, "product", "product_product_no_key")
        assert not _has_regular_unique(eng, "share_token", "share_token_token_key")
        # 仅保留 partial UNIQUE。
        assert _has_partial_unique_index(eng, "product", "idx_product_no_active")
        assert _has_partial_unique_index(eng, "share_token", "idx_share_token_token")
        with eng.connect() as conn:
            ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert ver == "0012_product_scene_image_partial_unique"
    finally:
        _reset_schema(url)


def test_old_db_upgrade_head_converges_to_same_schema():
    url = _safe_url()
    _reset_schema(url)
    # 模拟“已执行旧 0001（含普通 UNIQUE）”的库：升到 0001 后手动补建普通 UNIQUE。
    alembic_upgrade(url, "0001_initial")
    eng = create_engine(to_sync_url(url))
    with eng.begin() as conn:
        conn.execute(
            text("ALTER TABLE product ADD CONSTRAINT product_product_no_key UNIQUE (product_no)")
        )
        conn.execute(
            text("ALTER TABLE share_token ADD CONSTRAINT share_token_token_key UNIQUE (token)")
        )
    # 旧库确认存在普通 UNIQUE。
    assert _has_regular_unique(eng, "product", "product_product_no_key")
    assert _has_regular_unique(eng, "share_token", "share_token_token_key")
    # 升级到 head：0005 移除普通 UNIQUE。
    alembic_upgrade(url, "head")
    try:
        missing = EXPECTED_TABLES - _table_names(eng)
        assert not missing, f"missing tables: {missing}"
        assert not _has_regular_unique(eng, "product", "product_product_no_key")
        assert not _has_regular_unique(eng, "share_token", "share_token_token_key")
        assert _has_partial_unique_index(eng, "product", "idx_product_no_active")
        assert _has_partial_unique_index(eng, "share_token", "idx_share_token_token")
    finally:
        _reset_schema(url)


def test_teardown_leaves_consistent_empty_schema_and_upgrade_restores():
    """Task 2：teardown 不留下 alembic_version=head 但缺业务表的状态。"""
    url = _safe_url()
    _reset_schema(url)
    alembic_upgrade(url, "head")
    eng = create_engine(to_sync_url(url))
    try:
        assert EXPECTED_TABLES <= _table_names(eng)

        # 模拟 teardown：DROP SCHEMA public CASCADE + CREATE SCHEMA public。
        _reset_schema(url)
        # alembic_version 被一并清理，不得留下“head 但无表”。
        assert not _has_alembic_version(eng)
        assert "alembic_version" not in _table_names(eng)

        # 空 public schema 是合法一致状态；随后 alembic upgrade head 可完整恢复。
        alembic_upgrade(url, "head")
        assert EXPECTED_TABLES <= _table_names(eng)
        with eng.connect() as conn:
            ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert ver == "0012_product_scene_image_partial_unique"
    finally:
        _reset_schema(url)


def test_0005_downgrade_is_data_unsafe_with_soft_deleted_duplicates():
    """Task 7：0005 downgrade 重建普通 UNIQUE，若已有软删除重复数据则会失败。

    这证明 downgrade 并非“幂等安全”；正式发布以 forward-only 迁移为准，
    不依赖 downgrade 路径恢复历史约束。
    """
    from sqlalchemy.exc import IntegrityError, ProgrammingError

    url = _safe_url()
    _reset_schema(url)
    alembic_upgrade(url, "head")
    eng = create_engine(to_sync_url(url))
    try:
        with eng.begin() as conn:
            brand_id = str(uuid4())
            supplier_id = str(uuid4())
            category_id = str(uuid4())
            conn.execute(
                text(
                    "INSERT INTO brand (id, brand_name, create_time, update_time, is_deleted) "
                    "VALUES (:id,'B',now(),now(),false)"
                ),
                {"id": brand_id},
            )
            conn.execute(
                text(
                    "INSERT INTO supplier (id, supplier_name, cooperation_status, create_time, "
                    "update_time, is_deleted) VALUES (:id,'S','active',now(),now(),false)"
                ),
                {"id": supplier_id},
            )
            conn.execute(
                text(
                    "INSERT INTO category (id, category_name, level, sort, "
                    "create_time, update_time, is_deleted) "
                    "VALUES (:id,'C',1,1,now(),now(),false)"
                ),
                {"id": category_id},
            )
            # 第一个产品，编号 P1，随后软删除。
            conn.execute(
                text(
                    "INSERT INTO product (id, product_no, product_name, brand_id, "
                    "supplier_id, category_id, face_price, stock_status, status, "
                    "create_time, update_time, is_deleted) "
                    "VALUES (:id,'P1','p1',:b,:s,:c,1.0,'in_stock','active',"
                    "now(),now(),false)"
                ),
                {"id": str(uuid4()), "b": brand_id, "s": supplier_id, "c": category_id},
            )
            conn.execute(text("UPDATE product SET is_deleted=true WHERE product_no='P1'"))
            # 第二个产品，同编号 P1（partial unique 允许，因第一个已软删除）。
            conn.execute(
                text(
                    "INSERT INTO product (id, product_no, product_name, brand_id, "
                    "supplier_id, category_id, face_price, stock_status, status, "
                    "create_time, update_time, is_deleted) "
                    "VALUES (:id,'P1','p2',:b,:s,:c,2.0,'in_stock','active',"
                    "now(),now(),false)"
                ),
                {"id": str(uuid4()), "b": brand_id, "s": supplier_id, "c": category_id},
            )
        # downgrade 重建 product_product_no_key -> 物理重复 -> 失败。
        with pytest.raises((IntegrityError, ProgrammingError)):
            alembic_downgrade(url, "0004_seed_data")
    finally:
        _reset_schema(url)
