from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.documents.base import KnowledgeDocumentUpserter
from app.knowledge.documents.manual_provider import ProductManualKnowledgeProvider
from app.knowledge.documents.product_card import DatabaseProductFactProvider
from app.models.product import Product, ProductManual


async def upsert_product_card(db: AsyncSession, product_id: UUID):
    provider = DatabaseProductFactProvider(db)
    upserter = KnowledgeDocumentUpserter(db)
    document = await upserter.upsert(await provider.build_product_card(product_id))
    await db.flush()
    return document


async def backfill_product_manual(db: AsyncSession, manual_id: UUID):
    provider = ProductManualKnowledgeProvider(db)
    upserter = KnowledgeDocumentUpserter(db)
    document = await upserter.upsert(await provider.build(manual_id))
    await db.flush()
    return document


async def backfill_all_product_cards(db: AsyncSession) -> list[UUID]:
    result = await db.execute(select(Product.id).where(Product.is_deleted.is_(False)))
    ids = [row[0] for row in result.all()]
    for product_id in ids:
        await upsert_product_card(db, product_id)
    return ids


async def backfill_all_product_manuals(db: AsyncSession) -> list[UUID]:
    result = await db.execute(select(ProductManual.id).where(ProductManual.is_deleted.is_(False)))
    ids = [row[0] for row in result.all()]
    for manual_id in ids:
        await backfill_product_manual(db, manual_id)
    return ids
