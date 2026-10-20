from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token
from app.knowledge.errors import KnowledgeErrorCode, KnowledgeGatewayError
from app.knowledge.facets import FACET_QUERY_ALIASES, SHAPE_TAG_TYPES, ProductFacets
from app.knowledge.schemas import Fact, Source
from app.knowledge.tools.base import ToolContext, ToolDefinition
from app.models.product import (
    Brand,
    Category,
    Product,
    ProductImage,
    ProductTag,
    Supplier,
    Tag,
)

_PREVIEW_EXPIRE_SECONDS = 900
_CONTENT_TOKEN_SCOPE = "file_content"

# 搜索工具支持的等值过滤字段
_SEARCH_FILTER_FIELDS = (
    "status", "stock_status", "completeness_status", "category_id",
    "brand_id", "supplier_id", "material",
)

# 产品卡中允许作为独立事实回填的字段（字段名与 _product_card 输出一一对应）
_CARD_FACT_FIELDS = (
    "product_no", "product_name", "face_price_display", "stock_status_display",
    "status", "completeness_status", "material", "specification", "colors",
    "cost_price", "supplier_name",
)

PRODUCT_SEARCH_ALIASES = {
    "办公桌": ("办公桌", "班台", "总裁桌", "独立主管桌", "洽谈桌", "会议桌"),
    "桌子": ("办公桌", "班台", "总裁桌", "独立主管桌", "洽谈桌", "会议桌"),
}

SPECIFICATION_LENGTH_RE = re.compile(r"\bW\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
SPECIFICATION_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")


class ProductSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keyword: str | None = None
    keywords: list[str] = Field(default_factory=list, max_length=20)
    product_nos: list[str] = Field(default_factory=list, max_length=20)
    product_ids: list[UUID] = Field(default_factory=list, max_length=20)
    filters: dict[str, Any] = Field(default_factory=dict)
    facets: ProductFacets = Field(default_factory=ProductFacets)
    sort_by: str | None = None
    sort_order: str | None = None
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
        stmt = _build_product_search_statement(params)
        rows = (await context.db.execute(stmt)).scalars().all()
        if params.sort_by == "specification_length":
            rows.sort(
                key=lambda product: _specification_length_mm(product.specification) or 0,
                reverse=params.sort_order == "desc",
            )
            rows.sort(key=lambda product: _specification_length_mm(product.specification) is None)
        return _product_payload(rows, context.current_user)


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
            raise KnowledgeGatewayError(
                KnowledgeErrorCode.PLAN_INVALID, "缺少产品编号或 ID", status_code=400
            )
        stmt = stmt.where(or_(*conds)).limit(20)
        rows = (await context.db.execute(stmt)).scalars().all()
        return _product_payload(rows, context.current_user)


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
        inner = ProductGetManyInput(
            product_ids=params.product_ids, product_nos=params.product_nos
        )
        return await ProductGetManyTool().run(inner, context)


def _base_product_stmt():
    return select(Product).options(
        selectinload(Product.brand),
        selectinload(Product.category),
        selectinload(Product.supplier),
        selectinload(Product.tags),
        selectinload(Product.images).joinedload(ProductImage.attachment),
    ).where(Product.is_deleted.is_(False))


def _build_product_search_statement(params: ProductSearchInput):
    stmt = _base_product_stmt()
    if params.product_ids:
        stmt = stmt.where(Product.id.in_(params.product_ids))
    if params.product_nos:
        stmt = stmt.where(Product.product_no.in_(params.product_nos))
    keywords = params.keywords or []
    keyword = params.keyword or params.filters.get("keyword")
    if keyword and not keywords:
        keywords = [keyword]
    for item in keywords:
        stmt = stmt.where(_search_term(item))
    for field in _SEARCH_FILTER_FIELDS:
        value = params.filters.get(field)
        if value:
            stmt = stmt.where(getattr(Product, field) == value)
    if params.filters.get("face_price_min") is not None:
        stmt = stmt.where(Product.face_price >= params.filters["face_price_min"])
    if params.filters.get("face_price_max") is not None:
        stmt = stmt.where(Product.face_price <= params.filters["face_price_max"])
    stmt = _apply_product_facets(stmt, params.facets)
    if params.sort_by == "face_price":
        direction = (
            Product.face_price.desc()
            if params.sort_order == "desc"
            else Product.face_price.asc()
        )
        stmt = stmt.order_by(case((Product.face_price == 99999, 1), else_=0), direction)
    return stmt.limit(min(params.limit, 100))


def _apply_product_facets(stmt, facets: ProductFacets):
    if facets.category:
        category_names = {
            alias
            for canonical in facets.category
            for alias in FACET_QUERY_ALIASES["category"][canonical]
        }
        category_tree = (
            select(Category.id.label("id"), Category.parent_id.label("parent_id"))
            .where(
                func.lower(func.trim(Category.category_name)).in_(
                    [name.casefold() for name in category_names]
                ),
                Category.is_deleted.is_(False),
            )
            .cte(name="category_tree", recursive=True)
        )
        descendants = (
            select(Category.id, Category.parent_id)
            .join(category_tree, Category.parent_id == category_tree.c.id)
            .where(Category.is_deleted.is_(False))
        )
        category_tree = category_tree.union(descendants)
        stmt = stmt.where(Product.category_id.in_(select(category_tree.c.id)))

    if facets.shape:
        shape_names = {
            alias
            for canonical in facets.shape
            for alias in FACET_QUERY_ALIASES["shape"][canonical]
        }
        matching_products = select(ProductTag.product_id).join(
            Tag, Tag.id == ProductTag.tag_id
        ).where(
            ProductTag.product_id == Product.id,
            ProductTag.is_deleted.is_(False),
            func.lower(func.trim(Tag.tag_name)).in_([name.casefold() for name in shape_names]),
            Tag.tag_type.in_(SHAPE_TAG_TYPES),
            Tag.is_deleted.is_(False),
        )
        stmt = stmt.where(Product.id.in_(matching_products))
    return stmt


def _search_term(keyword: str):
    terms = PRODUCT_SEARCH_ALIASES.get(keyword, (keyword,))
    return or_(*(_search_term_exact(term) for term in terms))


def _search_term_exact(term: str):
    like = f"%{term}%"
    return or_(
        Product.product_no.ilike(like),
        Product.product_name.ilike(like),
        Product.description.ilike(like),
        Product.material.ilike(like),
        Product.specification.ilike(like),
        Product.category.has(Category.category_name.ilike(like)),
        Product.brand.has(Brand.brand_name.ilike(like)),
        Product.supplier.has(Supplier.supplier_name.ilike(like)),
        Product.tags.any(
            Tag.tag_name.ilike(like) & Tag.is_deleted.is_(False)
        ),
    )


def _specification_length_mm(specification: str | None) -> float | None:
    if not specification:
        return None
    match = SPECIFICATION_LENGTH_RE.search(specification) or SPECIFICATION_NUMBER_RE.search(
        specification
    )
    return float(match.group(1)) if match else None


def _product_payload(products: list[Product], current_user: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(UTC)
    cards: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for p in products:
        sid = f"db_product_{p.id}"
        card = _product_card(p, current_user)
        cards.append(card)
        sources.append(
            Source(
                source_id=sid,
                source_type="database_fact",
                title=f"产品当前事实: {p.product_no}",
                product_id=str(p.id),
                observed_at=now,
                access_policy="role_projected",
            ).model_dump(mode="json")
        )
        for name in _CARD_FACT_FIELDS:
            if name in card:
                facts.append(
                    Fact(
                        source_id=sid,
                        name=name,
                        value=card[name],
                        observed_at=now,
                        product_id=str(p.id),
                    ).model_dump(mode="json")
                )
    return {"products": cards, "facts": facts, "sources": sources}


def _product_card(p: Product, current_user: dict[str, Any]) -> dict[str, Any]:
    cover = p.cover_image
    attachment = cover.attachment if cover else None
    cover_image_url = None
    if attachment and not attachment.is_deleted:
        token = create_access_token(
            {
                "sub": current_user.get("sub") or current_user.get("user_id") or "file-content",
                "scope": _CONTENT_TOKEN_SCOPE,
                "attachment_id": str(attachment.id),
            },
            expires_delta=timedelta(seconds=_PREVIEW_EXPIRE_SECONDS),
        )
        cover_image_url = f"/api/v1/files/{attachment.id}/content?token={token}"
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
        "specification_length_mm": _specification_length_mm(p.specification),
        "colors": p.colors,
        "description": p.description,
        "tags": [
            tag.tag_name
            for tag in getattr(p, "tags", [])
            if not getattr(tag, "is_deleted", False)
        ],
        "cover_image_url": cover_image_url,
    }
