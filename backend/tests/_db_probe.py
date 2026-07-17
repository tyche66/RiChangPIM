"""Shared DB reachability + test-database safety helpers (integration layer).

This module MUST NOT import ``app`` or any SQLAlchemy ORM models. It is imported
by the integration conftest/fixtures (at test-session time) AND by a pure unit
test (``tests/unit/test_db_probe.py``) that runs with **no database** and **no
app import**.

Design goals (per the test-infra remediation brief):
- No network access at import / collection time. ``probe_postgres_reachable`` is
  only ever called from inside fixtures, never during ``pytest --collect-only``.
- ``TEST_DATABASE_URL`` always takes priority over any default, so tests can never
  accidentally point at the dev/prod ``DATABASE_URL``.
- We only ever create/drop schema on a database whose name carries a ``test``
  marker, OR on a target explicitly confirmed via a dedicated approval env var.
  This prevents accidental teardown of dev/prod databases.
- The reachability probe uses ``asyncpg`` (already required by the app) under a
  short timeout, so a missing/unreachable server fails fast instead of hanging
  test collection.
"""

from __future__ import annotations

import asyncio
import os
import urllib.parse

TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"
TEST_DB_APPROVED_ENV = "AI_PIM_TEST_DB_APPROVED"

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://pim:pim_password@localhost:5432/ai_pim_test"


def resolve_test_database_url() -> str:
    """Return the asyncpg DSN to use for tests.

    ``TEST_DATABASE_URL`` wins unconditionally. This guarantees the operator can
    never accidentally run integration tests against the dev/prod ``DATABASE_URL``.
    """
    return os.environ.get(TEST_DATABASE_URL_ENV, DEFAULT_TEST_DATABASE_URL)


def to_sync_url(url: str) -> str:
    """Normalise a SQLAlchemy DSN into a sync-driver form Alembic can use.

    Alembic runs migrations with a *synchronous* DBAPI. ``requirements.txt`` pins
    psycopg2 (SQLAlchemy's default postgresql driver), so ``+asyncpg`` / ``+psycopg``
    are replaced with the sync ``postgresql://`` (psycopg2) form. This is done
    unconditionally: under ``-W error::DeprecationWarning`` the psycopg2 import can
    itself emit a warning, which would otherwise flip the detection to asyncpg and
    surface as a cross-event-loop ``MissingGreenlet`` error.
    """
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
    )


def database_name_from_url(url: str) -> str:
    """Extract the database name from a SQLAlchemy/asyncpg DSN (last path segment)."""
    rest = url.split("?", 1)[0].split("#", 1)[0]
    return urllib.parse.urlparse(rest).path.strip("/").split("/")[-1]


def is_safe_test_database(url: str, approved_env: str = TEST_DB_APPROVED_ENV) -> bool:
    """True iff it is safe to create/drop schema on ``url``.

    Safe when the database name contains the literal ``test`` (case-insensitive),
    OR the dedicated approval env var ``AI_PIM_TEST_DB_APPROVED`` is set to a
    truthy value (explicit operator confirmation of a non-``test``-named DB).
    """
    name = database_name_from_url(url)
    if "test" in name.lower():
        return True
    approved = os.environ.get(approved_env, "").strip().lower()
    return approved in ("1", "true", "yes", "on")


async def _async_reach(asyncpg_url: str, timeout: float) -> bool:
    import asyncpg

    conn = None
    try:
        conn = await asyncpg.connect(asyncpg_url, timeout=timeout, command_timeout=timeout)
        await conn.fetchval("SELECT 1")
        return True
    except Exception:
        return False
    finally:
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass


def probe_postgres_reachable(url: str, timeout: float = 5.0) -> bool:
    """Lightweight synchronous reachability probe (``SELECT 1``).

    Uses asyncpg under a short timeout so a missing/unreachable server fails fast
    instead of hanging. Never called at import/collection time.
    """
    return asyncio.run(_async_reach(to_sync_url(url), timeout))


def evaluate_test_database(url: str | None = None, timeout: float = 5.0):
    """Return ``(ok, reason)``.

    ``ok`` is True only when the database is both SAFE (test DB or approved) and
    REACHABLE. ``reason`` is a human-readable explanation suitable for
    ``pytest.skip``.
    """
    if url is None:
        url = resolve_test_database_url()
    if not is_safe_test_database(url):
        name = database_name_from_url(url)
        return (
            False,
            f"refusing to operate on non-test database {name!r}; "
            f"set TEST_DATABASE_URL to a database whose name contains 'test', "
            f"or set {TEST_DB_APPROVED_ENV}=1 to confirm this target",
        )
    if not probe_postgres_reachable(url, timeout=timeout):
        return (
            False,
            f"no reachable Postgres at {url} (TEST_DATABASE_URL); skipping DB integration tests",
        )
    return (True, "")


def _make_alembic_cfg(url: str, ini: str = "alembic.ini"):
    from alembic.config import Config

    cfg = Config(ini)
    cfg.set_main_option("script_location", "alembic")
    cfg.set_main_option("sqlalchemy.url", to_sync_url(url))
    return cfg


def alembic_upgrade(url: str, rev: str = "head", ini: str = "alembic.ini") -> None:
    from alembic import command

    _run_alembic(command.upgrade, url, rev, ini)


def alembic_downgrade(url: str, rev: str, ini: str = "alembic.ini") -> None:
    from alembic import command

    _run_alembic(command.downgrade, url, rev, ini)


def _run_alembic(fn, url: str, rev: str, ini: str) -> None:
    """Run an Alembic command while keeping process env isolated.

    ``ALEMBIC_OVERRIDE_URL`` is only ever set for the duration of the single
    Alembic command and restored afterwards (removed if it was absent, or
    reverted to its previous value). This prevents a test's target DB from
    leaking into later migrations / the app's runtime configuration via a
    stale process-environment override.
    """
    prev = os.environ.get("ALEMBIC_OVERRIDE_URL")
    os.environ["ALEMBIC_OVERRIDE_URL"] = to_sync_url(url)
    try:
        fn(_make_alembic_cfg(url, ini), rev)
    finally:
        if prev is None:
            os.environ.pop("ALEMBIC_OVERRIDE_URL", None)
        else:
            os.environ["ALEMBIC_OVERRIDE_URL"] = prev
