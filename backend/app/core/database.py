from __future__ import annotations

from importlib import import_module

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import settings


def _load_pgvector_type():
    try:
        vector_module = import_module("pgvector.sqlalchemy.vector")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "pgvector is required for database bootstrap. Install backend/requirements.txt "
            "dependencies before importing app.core.database."
        ) from exc

    vector_type = getattr(vector_module, "VECTOR", None) or getattr(vector_module, "Vector", None)
    if vector_type is None:
        raise RuntimeError(
            "pgvector.sqlalchemy.vector.Vector/VECTOR is unavailable; "
            "cannot bootstrap vector columns."
        )
    return vector_type


def _load_pgvector_halfvec_type():
    vector_module = import_module("pgvector.sqlalchemy")
    halfvec_type = getattr(vector_module, "HALFVEC", None)
    return halfvec_type or vector_module.HalfVector


Vector = _load_pgvector_type()
HalfVector = _load_pgvector_halfvec_type()

engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
