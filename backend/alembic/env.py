import os
from alembic import context
from sqlalchemy import pool, engine_from_config
from logging.config import fileConfig

import sys
from os.path import abspath, dirname

sys.path.insert(0, dirname(dirname(abspath(__file__))))

from app.core.database import Base
from app.core.config import settings
from app.models.user import User, Role, Permission, RolePermission
from app.models.product import Product, Category, Brand, Supplier, Tag, ProductTag, Attachment, ProductImage, ProductManual
from app.models.doc_chunk import ProductManualChunk
from app.models.sales import Proposal, ProposalItem, Quotation, QuotationItem
from app.models.audit import Share, ShareToken, ShareLog, Visitor, OperationLog, AIConversation

target_metadata = Base.metadata


def _to_sync_url(url: str) -> str:
    """Alembic runs migrations synchronously; force the sync psycopg2 driver.

    ``requirements.txt`` pins psycopg2 (SQLAlchemy's default postgresql driver),
    so both ``+asyncpg`` and ``+psycopg`` are normalised to the plain
    ``postgresql://`` (psycopg2) scheme. Using an async driver here raises
    ``MissingGreenlet`` because there is no event loop for Alembic to await on.
    """
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
    )


def _resolve_url() -> str:
    """Resolve the DSN Alembic migrates against.

    Priority:
      1. ``ALEMBIC_OVERRIDE_URL`` (env var) — used by the test harness to target
         the isolated ``ai_pim_test`` database regardless of the app config.
      2. ``settings.DATABASE_URL`` — keeps ``alembic upgrade head`` consistent
         with the deployed runtime configuration.
      3. ``alembic.ini``'s hardcoded ``sqlalchemy.url`` — final fallback.

    All sources are coerced to the synchronous psycopg2 form so migrations work
    both locally and in container/server deployments without manual edits.
    """
    override = os.environ.get("ALEMBIC_OVERRIDE_URL")
    if override:
        sync_url = _to_sync_url(override)
        context.config.set_main_option("sqlalchemy.url", sync_url)
        return sync_url
    url = getattr(settings, "DATABASE_URL", "") or ""
    if url:
        sync_url = _to_sync_url(url)
        context.config.set_main_option("sqlalchemy.url", sync_url)
        return sync_url
    return context.config.get_main_option("sqlalchemy.url")


def run_migrations_offline():
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    _resolve_url()
    connectable = engine_from_config(
        context.config.get_section(context.config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
