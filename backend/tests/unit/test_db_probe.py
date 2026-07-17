"""Unit tests for the DB skip-determination logic in ``tests/_db_probe.py``.

These run with NO database and NO app import (pure unit layer, docs/09-测试计划
§1.1). They pin the rules that decide whether an integration test is skipped:

- ``TEST_DATABASE_URL`` always wins over the default.
- A database is only considered safe when its name contains ``test``, or when the
  dedicated ``AI_PIM_TEST_DB_APPROVED`` env var explicitly confirms it.
- ``probe_postgres_reachable`` must return ``False`` (never hang / never raise)
  when no server is listening, so collection stays DB-free.
"""

import os

import pytest
from _db_probe import (
    alembic_downgrade,
    alembic_upgrade,
    database_name_from_url,
    is_safe_test_database,
    probe_postgres_reachable,
    resolve_test_database_url,
)


def test_resolve_test_database_url_prefers_env(monkeypatch):
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://u:p@localhost:5432/my_app_test",
    )
    assert resolve_test_database_url() == "postgresql+asyncpg://u:p@localhost:5432/my_app_test"


def test_database_name_from_url_parses_asyncpg_dsn():
    assert database_name_from_url("postgresql+asyncpg://u:p@db:5432/ai_pim_test") == "ai_pim_test"


def test_database_name_from_url_ignores_query():
    assert database_name_from_url("postgresql://u:p@db:5432/ai_pim_test?ssl=1") == "ai_pim_test"


def test_is_safe_test_database_true_for_test_named():
    assert is_safe_test_database("postgresql://u:p@db:5432/ai_pim_test") is True
    assert is_safe_test_database("postgresql://u:p@db:5432/test_db") is True
    assert is_safe_test_database("postgresql://u:p@db:5432/UNIT_TEST") is True


def test_is_safe_test_database_false_for_prod_unless_approved(monkeypatch):
    monkeypatch.delenv("AI_PIM_TEST_DB_APPROVED", raising=False)
    assert is_safe_test_database("postgresql://u:p@db:5432/ai_pim") is False
    assert is_safe_test_database("postgresql://u:p@db:5432/production") is False

    monkeypatch.setenv("AI_PIM_TEST_DB_APPROVED", "1")
    assert is_safe_test_database("postgresql://u:p@db:5432/ai_pim") is True


def test_probe_unreachable_returns_false_fast():
    # Port 1 never listens; asyncpg should fail fast (no hang, no raise).
    assert (
        probe_postgres_reachable("postgresql+asyncpg://u:p@127.0.0.1:1/none", timeout=1.0) is False
    )


def test_alembic_upgrade_restores_env_when_absent(monkeypatch):
    import alembic.command as cmd

    captured = {}

    def fake_upgrade(cfg, rev):
        captured["url"] = os.environ.get("ALEMBIC_OVERRIDE_URL")
        captured["rev"] = rev

    monkeypatch.delenv("ALEMBIC_OVERRIDE_URL", raising=False)
    monkeypatch.setattr(cmd, "upgrade", fake_upgrade)
    alembic_upgrade("postgresql://u:p@db:5432/ai_pim_test", "head")
    assert captured["rev"] == "head"
    assert captured["url"] == "postgresql://u:p@db:5432/ai_pim_test"
    # 调用结束后进程环境恢复：原变量不存在则删除。
    assert "ALEMBIC_OVERRIDE_URL" not in os.environ


def test_alembic_upgrade_restores_env_when_present(monkeypatch):
    import alembic.command as cmd

    monkeypatch.setenv("ALEMBIC_OVERRIDE_URL", "postgresql://orig/db")
    monkeypatch.setattr(cmd, "upgrade", lambda cfg, rev: None)
    alembic_upgrade("postgresql://u:p@db:5432/ai_pim_test", "head")
    # 原变量已存在则恢复原值，不被测试库覆盖。
    assert os.environ["ALEMBIC_OVERRIDE_URL"] == "postgresql://orig/db"


def test_alembic_downgrade_restores_env_when_absent(monkeypatch):
    import alembic.command as cmd

    monkeypatch.delenv("ALEMBIC_OVERRIDE_URL", raising=False)
    monkeypatch.setattr(cmd, "downgrade", lambda cfg, rev: None)
    alembic_downgrade("postgresql://u:p@db:5432/ai_pim_test", "0003_x")
    assert "ALEMBIC_OVERRIDE_URL" not in os.environ


def test_alembic_upgrade_restores_env_on_exception(monkeypatch):
    import alembic.command as cmd

    monkeypatch.delenv("ALEMBIC_OVERRIDE_URL", raising=False)

    def boom(cfg, rev):
        raise RuntimeError("migration failed")

    monkeypatch.setattr(cmd, "upgrade", boom)
    with pytest.raises(RuntimeError):
        alembic_upgrade("postgresql://u:p@db:5432/ai_pim_test", "head")
    # 即使 Alembic command 抛异常，环境也必须恢复。
    assert "ALEMBIC_OVERRIDE_URL" not in os.environ
