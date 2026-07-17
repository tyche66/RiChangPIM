"""Unit test layer configuration (docs/09-测试计划 §1.1).

This conftest is intentionally minimal and MUST NOT import anything from
``app.main`` or ``app.core.database`` — unit tests must run without any
DATABASE_URL / REDIS_URL / MINIO environment variables and in <5s.

If a unit test needs an ``app.*`` symbol, it must import only the leaf module
that contains it (e.g. ``app.core.serializers``, ``app.services.rag_index``,
``app.adapters.none``) and that leaf must NOT transitively import
``app.main`` / ``app.core.database``. If such a transitive dependency is
discovered, fix the import chain in the application, do not pull the whole app
into the unit layer.

Integration fixtures (``client`` / ``integration_setup_db``) live in the
parent ``tests/conftest.py`` and are lazily wired so they never load during
unit collection.
"""
