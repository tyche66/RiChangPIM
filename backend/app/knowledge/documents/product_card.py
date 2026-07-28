from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.knowledge.documents.base import (
    KnowledgeChunkPayload,
    KnowledgeDocumentPayload,
    ProductFactProvider,
    stable_content_hash,
)
from app.models.product import Product

SENSITIVE_PRODUCT_FIELDS = {
    "face_price",
    "cost_price",
    "stock_status",
    "supplier_id",
    "supplier_name",
    "status",
}


class DatabaseProductFactProvider(ProductFactProvider):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_product_card(self, product_id: UUID) -> KnowledgeDocumentPayload:
        result = await self.db.execute(
            select(Product)
            .options(
                selectinload(Product.brand),
                selectinload(Product.category),
                selectinload(Product.tags),
            )
            .where(Product.id == product_id, Product.is_deleted.is_(False))
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise ValueError(f"Product {product_id} not found")

        facts = {
            "product_name": product.product_name,
            "product_no": product.product_no,
            "brand": product.brand.brand_name if product.brand else None,
            "category": product.category.category_name if product.category else None,
            "material": product.material or None,
            "specification": product.specification or None,
            "colors": product.colors or None,
            "tags": sorted(tag.tag_name for tag in product.tags if not tag.is_deleted),
            "description": product.description or None,
        }
        # Drop empty values so content hash and chunk text stay stable.
        facts = {key: value for key, value in facts.items() if value not in (None, "", [])}

        chunk_text = self._render_card_text(facts)
        content_hash = stable_content_hash(
            {
                "source_type": "product_card",
                "source_id": str(product.id),
                "facts": facts,
            }
        )
        return KnowledgeDocumentPayload(
            source_type="product_card",
            source_id=product.id,
            product_id=product.id,
            category_id=product.category_id,
            brand_id=product.brand_id,
            title=f"{product.product_name} 产品知识卡片",
            doc_type="product_card",
            content_hash=content_hash,
            parse_status="parsed",
            index_status="indexed",
            metadata={"fact_keys": list(facts), "source": "pim_product"},
            chunks=[
                KnowledgeChunkPayload(
                    chunk_index=0,
                    chunk_text=chunk_text,
                    chunk_type="product_card",
                    section_path="product_card",
                    token_count=len(chunk_text),
                    metadata={"fact_keys": list(facts)},
                )
            ],
        )

    @staticmethod
    def _render_card_text(facts: dict[str, object]) -> str:
        labels = {
            "product_name": "产品名称",
            "product_no": "产品编号",
            "brand": "品牌",
            "category": "类目",
            "material": "材质",
            "specification": "规格",
            "colors": "颜色",
            "tags": "标签",
            "description": "产品描述",
            "applicable_scene": "适用场景",
        }
        lines: list[str] = []
        for key in [
            "product_name",
            "product_no",
            "brand",
            "category",
            "material",
            "specification",
            "colors",
            "tags",
            "description",
            "applicable_scene",
        ]:
            if key not in facts:
                continue
            value = facts[key]
            if isinstance(value, list):
                rendered = "、".join(str(item) for item in value)
            else:
                rendered = str(value)
            lines.append(f"{labels[key]}: {rendered}")
        return "\n".join(lines)
