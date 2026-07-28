from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.knowledge.schemas import Fact, Source
from app.knowledge.tools.base import ToolContext, ToolDefinition
from app.models.product import Product, Supplier


class SupplierCompareInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[UUID] = Field(default_factory=list, max_length=20)
    product_nos: list[str] = Field(default_factory=list, max_length=20)
    supplier_ids: list[UUID] = Field(default_factory=list, max_length=20)


class SupplierCompareTool:
    definition = ToolDefinition(
        name="supplier.compare",
        version="1.0",
        description="采购供应商只读比较，缺失交期/质量/实时库存时显式返回 unknown",
        input_schema=SupplierCompareInput,
        required_permissions={"ai:procurement", "supplier:view"},
        risk_level="medium",
        read_only=True,
        max_results=20,
        timeout_ms=1000,
        field_projection=False,
        audit_event="knowledge.tool.supplier.compare",
    )

    async def run(self, params: SupplierCompareInput, context: ToolContext) -> dict[str, Any]:
        supplier_ids = set(params.supplier_ids)
        product_stmt = None
        if params.product_ids or params.product_nos:
            product_stmt = (
                select(Product)
                .options(selectinload(Product.supplier))
                .where(Product.is_deleted.is_(False))
            )
            if params.product_ids:
                product_stmt = product_stmt.where(Product.id.in_(params.product_ids))
            if params.product_nos:
                product_stmt = product_stmt.where(Product.product_no.in_(params.product_nos))
            products = (await context.db.execute(product_stmt.limit(20))).scalars().all()
            supplier_ids |= {p.supplier_id for p in products}
        else:
            products = []

        supplier_stmt = select(Supplier).where(Supplier.is_deleted.is_(False))
        if supplier_ids:
            supplier_stmt = supplier_stmt.where(Supplier.id.in_(supplier_ids))
        suppliers = (await context.db.execute(supplier_stmt.limit(20))).scalars().all()
        product_by_supplier: dict[UUID, list[Product]] = {}
        for product in products:
            product_by_supplier.setdefault(product.supplier_id, []).append(product)

        source_id = "db_supplier_compare"
        rows = []
        facts = []
        for supplier in suppliers:
            related = product_by_supplier.get(supplier.id, [])
            row = {
                "supplier_id": str(supplier.id),
                "supplier_name": supplier.supplier_name,
                "cooperation_status": supplier.cooperation_status,
                "related_product_nos": [p.product_no for p in related],
                "lead_time": "unknown",
                "quality_rating": "unknown",
                "realtime_stock": "unknown",
                "unknown_fields": ["lead_time", "quality_rating", "realtime_stock"],
            }
            rows.append(row)
            facts.append(
                Fact(source_id=source_id, name="supplier_compare", value=row).model_dump(
                    mode="json"
                )
            )
        return {
            "facts": facts,
            "suppliers": rows,
            "sources": [
                Source(
                    source_id=source_id,
                    source_type="database_fact",
                    title="供应商当前结构化事实",
                    access_policy="role_projected",
                ).model_dump(mode="json")
            ],
        }
