"""Root pytest configuration for the integration test layer.

IMPORTANT: This conftest MUST NOT import ``app.main`` (or anything that pulls
``app.core.database``) at module top-level. Doing so would force every test
collected under ``tests/`` — including pure unit tests such as
``test_field_permission.py`` / ``test_rag_split.py`` / ``test_ai_adapter_dummy.py``
— to create an async DB engine and connect to Postgres during collection, which
times out (62s) in sandboxes/CI without a database (see docs/09-测试计划 §1.1
"单元测试不依赖 DB").

Therefore the app import and the async engine construction are deferred into the
fixtures that actually need them (``integration_setup_db`` and ``client``). Pure
unit tests that do not request those fixtures never touch the app or DB.

See ``tests/unit/conftest.py`` for the unit test layer marker that documents the
symmetric contract of NOT pulling in app/DB.
"""

import os

import pytest
from _db_probe import (
    is_safe_test_database,
    resolve_test_database_url,
)

# ---------------------------------------------------------------------------
# Unit-layer import safety net (docs/09-测试计划 §1.1 "单元测试不依赖 DB")
# ---------------------------------------------------------------------------
# Several pure unit tests transitively import ``app.core.config`` via the ORM
# model/db chain (e.g. test_rag_split -> app.services.rag_index -> app.models.*
# -> app.core.database -> app.core.config.Settings()). ``Settings`` is a
# pydantic BaseSettings instantiated at module import time and requires a few
# env vars to validate. We inject *dummy* values here — solely to satisfy
# Pydantic validation at import time — when the real environment does not
# provide them. These dummies NEVER cause an actual connection: unit tests do
# not request ``integration_setup_db`` / ``client`` / ``get_db``, so the async
# engine is constructed (cheap, defers connect) but never used. Integration
# tests override TEST_DATABASE_URL with a real DSN in the shell/CI.
#
# This is test-infra only; no app/ business code is modified.
#
# NOTE: ``TEST_DATABASE_URL`` is deliberately NOT seeded here. Integration tests
# resolve it via ``_db_probe.resolve_test_database_url`` (which defaults to a
# ``*_test`` database), and the operator points it at the real test DSN in the
# shell. Seeding a dummy ``TEST_DATABASE_URL`` here would only mask misconfig and
# could be mistaken for a real target.
_UNIT_TEST_ENV_DEFAULTS = {
    "DATABASE_URL": "postgresql+asyncpg://unit:unit@localhost:5432/unit_dummy",
    "REDIS_URL": "redis://localhost:6379/0",
    "JWT_SECRET": "unit-test-dummy-secret-not-for-prod",
    "MINIO_ENDPOINT": "localhost:9000",
    "MINIO_ACCESS_KEY": "unit",
    "MINIO_SECRET_KEY": "unit",
}
for _k, _v in _UNIT_TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_k, _v)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


def _test_database_url() -> str:
    # TEST_DATABASE_URL always wins (see _db_probe.resolve_test_database_url).
    return resolve_test_database_url()


@pytest.fixture(scope="session")
def _test_db_url():
    """Resolve + probe the test DB URL once per session; skip if unreachable/unsafe.

    This fixture does NOT create an async engine (engines must be created
    inside the same asyncio loop a test runs in — see ``_engine``). It only
    performs the reachability + safety probe so ``--collect-only`` stays
    free of any DB connection, and so we never mask a real infrastructure
    problem as a pass — nor operate on dev/prod.
    """
    url = _test_database_url()
    ok, reason = _evaluate_db(url)
    if not ok:
        pytest.skip(reason)
    return url


def _evaluate_db(url: str):
    from _db_probe import evaluate_test_database

    return evaluate_test_database(url)


@pytest.fixture
async def _engine(_test_db_url):
    """Per-test async engine, created INSIDE the test's own anyio loop.

    anyio runs each test (and its async fixtures) in a *fresh* event loop.
    An async engine bound to another loop raises ``MissingGreenlet`` when used
    across loops, so the engine MUST be created within the loop the test
    actually runs in — i.e. here, not in a session-scoped fixture.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(_test_db_url, echo=False, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def _sessionmaker(_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    return async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def integration_setup_db(_test_db_url):
    """Per-test isolated Postgres: reset schema + seed, drop after.

    Renamed from ``setup_db`` and no longer ``autouse=True``: only integration
    tests that explicitly request this fixture (directly, or via ``client``)
    connect to the database, per docs/09-测试计划 §1.1.

    Each test gets a *fresh* database so assertions on exact row counts
    (audit logs, proposals, …) are deterministic and never accumulate state
    across the session. The reset is ``DROP SCHEMA public CASCADE`` + one
    ``alembic upgrade head``, which also (re)creates the seed data via the
    0004 data migration — roles / permissions / role-permission mapping and the
    initial ``admin`` user (admin/admin123) that the smoke/e2e tests rely on.

    Teardown only drops schema when the target is a confirmed safe test database,
    so a misconfigured run can never delete a dev/prod database.
    """
    from _db_probe import alembic_upgrade, to_sync_url

    url = _test_db_url
    # 让应用引擎（audit 等直接用 AsyncSessionLocal）也指向同一测试库。
    os.environ["DATABASE_URL"] = to_sync_url(url)

    _reset_schema(url)
    alembic_upgrade(url, "head")

    yield url

    # Teardown: drop the entire public schema (tables + alembic_version together)
    # and recreate an empty one, so the test DB never ends up in the broken state
    # "alembic_version = head but business tables missing" that mixed
    # Base.metadata.drop_all + Alembic version tracking used to leave behind.
    # The destructive operation is gated by is_safe_test_database.
    _drop_schema(url)


def _reset_schema(url: str) -> None:
    """Drop and recreate the public schema so every test starts from empty.

    Uses a synchronous psycopg2 connection (Alembic runs synchronously anyway).
    Only ever called for a URL already vetted by ``is_safe_test_database``.
    """
    import psycopg2
    from _db_probe import to_sync_url

    sync_url = to_sync_url(url)
    conn = psycopg2.connect(sync_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        conn.close()



def _drop_schema(url: str) -> None:
    """Drop + recreate the public schema so the DB ends in a consistent state.

    Leaves the test DB as an *empty* public schema (no business tables, no
    alembic_version) — never the broken "alembic_version = head but tables
    missing" state. ``DROP SCHEMA public CASCADE`` also removes alembic_version,
    so a subsequent ``alembic upgrade head`` fully rebuilds from scratch.

    Only ever called for a URL already vetted by ``is_safe_test_database``.
    """
    import psycopg2
    from _db_probe import to_sync_url

    if not is_safe_test_database(url):
        return
    sync_url = to_sync_url(url)
    conn = psycopg2.connect(sync_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        conn.close()


@pytest.fixture
async def client(_engine, _sessionmaker, integration_setup_db):
    """ASGI test client wired to a per-test DB override.

    Lazily imports ``app.main`` so pure unit tests never import the app, and
    runs inside the test's own anyio loop so every async engine used here
    (business queries AND the audit middleware's ``AsyncSessionLocal``) is
    bound to that same loop — avoiding ``MissingGreenlet``.
    """
    from httpx import ASGITransport, AsyncClient

    import app.core.database as _db_mod
    from app.core.database import get_db
    from app.main import app

    # 让审计等直接用 AsyncSessionLocal 的模块也指向「当前测试 loop」的引擎，
    # 否则跨 loop 使用异步引擎会抛 MissingGreenlet。
    _original_engine = _db_mod.engine
    _original_sessionmaker = _db_mod.AsyncSessionLocal
    try:
        _db_mod.engine = _engine
        _db_mod.AsyncSessionLocal = _sessionmaker

        async def override_get_db():
            async with _sessionmaker() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
        # 恢复原始全局引用，防止已 dispose 的引擎/连接在后续测试中引发
        # 跨 event-loop 的关闭错误。
        _db_mod.engine = _original_engine
        _db_mod.AsyncSessionLocal = _original_sessionmaker


@pytest.fixture
async def db(_sessionmaker):
    """Async DB session with auto-rollback for integration tests.

    Each test gets a session with auto-rollback on teardown. Tests that
    explicitly call ``await db.commit()`` will persist changes — use sparingly.
    """
    session = _sessionmaker()
    try:
        yield session
    finally:
        # 仅在有活跃事务时回滚，避免已 commit 后再次 rollback 引发 PendingRollbackError；
        # 用 try/except 吞掉 teardown 阶段可能的跨 loop/引擎已 dispose 异常。
        try:
            if session.get_transaction():
                await session.rollback()
        except Exception:
            pass
        try:
            await session.close()
        except Exception:
            pass


@pytest.mark.anyio
async def test_health_check(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert "status" in data["data"]
    assert "version" in data["data"]
    assert "components" in data["data"]


@pytest.mark.anyio
async def test_login_wrong_password(client):
    resp = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_root(client):
    resp = await client.get("/")
    assert resp.status_code == 200
