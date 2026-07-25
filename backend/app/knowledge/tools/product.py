from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.knowledge.errors import KnowledgeErrorCode, KnowledgeGatewayError
from app.knowledge.schemas import Fact, Source
from app.knowledge.tools.base import ToolContext, ToolDefinition
from app.models.product import Brand, Category, Product, Supplier


class ProductSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keyword: str | None = None
    product_nos: list[str] = Field(default_factory=list, max_length=20)
    product_ids: list[UUID] = Field(default_factory=list, max_length=20)
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=20, ge=1, le=100)


class ProductGetManyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_ids: list[UUID] = Field(default_factory=list, max_length=20)
    product_nos: list[str] = Field(default_factory=list, max_length=20)


class ProductCompareInput(ProductGetManyInput):
    @model_validator(mode="after")
    def max_compare(self):
        total = len(self.product_ids) + len(self.product_nos)
        if total > 5:
            raise ValueError("product.compare 最多比较 5 个产品")
        return self


class ProductSearchTool:
    definition = ToolDefinition(
        name="product.search",
        version="1.0",
        description="结构化过滤和产品搜索",
        input_schema=ProductSearchInput,
        required_permissions={"ai:product", "product:view"},
        risk_level="low",
        read_only=True,
        max_results=100,
        timeout_ms=1000,
        field_projection=True,
        audit_event="knowledge.tool.product.search",
    )

    async def run(self, params: ProductSearchInput, context: ToolContext) -> dict[str, Any]:
        stmt = _base_product_stmt()
        if params.product_ids:
            stmt = stmt.where(Product.id.in_(params.product_ids))
        if params.product_nos:
            stmt = stmt.where(Product.product_no.in_(params.product_nos))
        keyword = params.keyword or params.filters.get("keyword")
        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(or_(Product.product_no.ilike(like), Product.product_name.ilike(like), Product.description.ilike(like), Product.material.ilike(like), Product.specification.ilike(like)))
        for field in ("status", "stock_status", "completeness_status", "category_id", "brand_id", "supplier_id", "material"):
            value = params.filters.get(field)
            if value:
                stmt = stmt.where(getattr(Product, field) == value)
        stmt = stmt.limit(min(params.limit, 100))
        rows = (await context.db.execute(stmt)).scalars().all()
        return _product_payload(rows)


class ProductGetManyTool:
    definition = ToolDefinition(
        name="product.get_many",
        version="1.0",
        description="批量读取当前产品事实",
        input_schema=ProductGetManyInput,
        required_permissions={"ai:product", "product:view"},
        risk_level="low",
        read_only=True,
        max_results=20,
        timeout_ms=1000,
        field_projection=True,
        audit_event="knowledge.tool.product.get_many",
    )

    async def run(self, params: ProductGetManyInput, context: ToolContext) -> dict[str, Any]:
        stmt = _base_product_stmt()
        conds = []
        if params.product_ids:
            conds.append(Product.id.in_(params.product_ids))
        if params.product_nos:
            conds.append(Product.product_no.in_(params.product_nos))
        if not conds:
            raise KnowledgeGatewayError(KnowledgeErrorCode.PLAN_INVALID, "缺少产品编号或 ID", status_code=400)
        stmt = stmt.where(or_(*conds)).limit(20)
        rows = (await context.db.execute(stmt)).scalars().all()
        return _product_payload(rows)


class ProductCompareTool:
    definition = ToolDefinition(
        name="product.compare",
        version="1.0",
        description="比较最多 5 个产品",
        input_schema=ProductCompareInput,
        required_permissions={"ai:product", "product:view"},
        risk_level="medium",
        read_only=True,
        max_results=5,
        timeout_ms=1000,
        field_projection=True,
        audit_event="knowledge.tool.product.compare",
    )

    async def run(self, params: ProductCompareInput, context: ToolContext) -> dict[str, Any]:
        return await ProductGetManyTool().run(ProductGetManyInput(product_ids=params.product_ids, product_nos=params.product_nos), context)


def _base_product_stmt():
    return select(Product).options(selectinload(Product.brand), selectinload(Product.category), selectinload(Product.supplier), selectinload(Product.images)).where(Product.is_deleted.is_(False))


def _product_payload(products: list[Product]) -> dict[str, Any]:
    now = datetime.now(UTC)
    cards: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for p in products:
        sid = f"db_product_{p.id}"
        card = _product_card(p)
        cards.append(card)
        sources.append(Source(source_id=sid, source_type="database_fact", title=f"产品当前事实: {p.product_no}", product_id=str(p.id), observed_at=now, access_policy="role_projected").model_dump(mode="json"))
        for name in ("product_no", "product_name", "face_price_display", "stock_status_display", "status", "completeness_status", "material", "specification", "colors", "cost_price", "supplier_name"):
            if name in card:
                facts.append(Fact(source_id=sid, name=name, value=card[name], observed_at=now, product_id=str(p.id)).model_dump(mode="json"))
    return {"products": cards, "facts": facts, "sources": sources}


def _product_card(p: Product) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "product_no": p.product_no,
        "product_name": p.product_name,
        "brand_id": str(p.brand_id),
        "brand_name": getattr(p.brand, "brand_name", None),
        "category_id": str(p.category_id),
        "category_name": getattr(p.category, "category_name", None),
        "supplier_id": str(p.supplier_id),
        "supplier_name": getattr(p.supplier, "supplier_name", None),
        "face_price_display": "待核价" if p.face_price == 99999 else p.face_price,
        "cost_price": p.cost_price,
        "material": p.material,
        "stock_status": p.stock_status,
        "stock_status_display": "库存待确认" if p.stock_status == "unknown" else p.stock_status,
        "status": p.status,
        "completeness_status": p.completeness_status,
        "specification": p.specification,
        "colors": p.colors,
        "description": p.description,
        "cover_image_url": None,
    }
