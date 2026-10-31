from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Float, and_, case, func, or_, select
from sqlalchemy.orm import aliased, selectinload

from app.core.security import create_access_token
from app.knowledge.attributes import (
    EMPTY_DICTIONARY,
    AttributeDictionary,
    HardFacet,
    NumericFilter,
    await_load_dictionary,
    normalize_text,
)
from app.knowledge.errors import KnowledgeErrorCode, KnowledgeGatewayError
from app.knowledge.schemas import Fact, Source
from app.knowledge.tools.base import ToolContext, ToolDefinition
from app.models.catalog_attribute import (
    CatalogAttributeDefinition,
    CatalogAttributeOption,
    ProductAttributeValue,
)
from app.models.product import (
    Brand,
    Category,
    Product,
    ProductImage,
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
    # 通用硬条件（Track A）。旧的 facets dict 仍被接受并归一到此结构。
    hard_facets: list[HardFacet] = Field(default_factory=list)
    numeric_filters: list[NumericFilter] = Field(default_factory=list)
    exclude_values: list[HardFacet] = Field(default_factory=list)
    facets: dict[str, Any] = Field(default_factory=dict)
    soft_terms: list[str] = Field(default_factory=list)
    unknown_terms: list[str] = Field(default_factory=list)
    sort_by: str | None = None
    sort_order: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    match_tier: str | None = None  # exact | partial | text_match | semantic

    @model_validator(mode="after")
    def _coerce_legacy_facets(self):
        """把旧的 ``facets={'shape': ['arc']}`` 归一成通用硬条件。

        兼容旧调用方；不会引入任何写死的维度。
        """
        if self.facets:
            values = self.facets.get("values", self.facets)
            if isinstance(values, dict):
                for attribute_code, options in values.items():
                    if not options:
                        continue
                    if any(
                        f.attribute_code == attribute_code for f in self.hard_facets
                    ):
                        continue
                    self.hard_facets.append(
                        HardFacet(
                            attribute_code=str(attribute_code),
                            values=[str(v) for v in options],
                            source="rule",
                        )
                    )
        return self


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
        dictionary = await _load_dictionary(context.db)

        # ---- 1) 结构化精确过滤（硬条件全部满足后才算 primary） -------------
        exact_stmt = _build_product_search_statement(params, dictionary, tier="exact")
        exact_rows = (await context.db.execute(exact_stmt)).scalars().all()

        # ---- 2) 宽松候选（仅在没有精确结果时单独返回，绝不混入 primary） --
        relaxed: list[tuple[Product, list[str]]] = []
        if not exact_rows and params.hard_facets:
            for index in range(len(params.hard_facets) - 1, -1, -1):
                partial_params = params.model_copy(
                    update={
                        "hard_facets": (
                            params.hard_facets[:index] + params.hard_facets[index + 1 :]
                        )
                    }
                )
                stmt = _build_product_search_statement(partial_params, dictionary, tier="partial")
                rows = (await context.db.execute(stmt)).scalars().all()
                for row in rows:
                    if row.id not in {r.id for r, _ in relaxed}:
                        relaxed.append(
                            (row, [f"放宽属性条件: {params.hard_facets[index].attribute_code}"])
                        )
                if relaxed:
                    break

        # ---- 3) 文本召回（软词相关；不作为属性命中） ---------------------
        text_rows: list[Product] = []
        if params.soft_terms and not exact_rows:
            text_rows = await _text_recall(context.db, params.soft_terms, params.limit)

        primary = list(exact_rows)
        payload = _product_payload(
            primary,
            context.current_user,
            match_tier="exact" if primary else None,
            params=params,
            dictionary=dictionary,
        )
        if relaxed:
            payload["relaxed_candidates"] = [
                {
                    **_product_card(row, context.current_user),
                    "match_tier": "partial",
                    "relaxed_conditions": reasons,
                }
                for row, reasons in relaxed[: params.limit]
            ]
        if text_rows and not primary:
            payload["text_candidates"] = [
                {
                    **_product_card(row, context.current_user),
                    "match_tier": "text_match",
                    "match_reason": "仅自由文本命中，未满足属性硬条件",
                }
                for row in text_rows[: params.limit]
            ]
        return payload


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
        selectinload(Product.attribute_values).selectinload(
            ProductAttributeValue.definition
        ),
        selectinload(Product.attribute_values).selectinload(ProductAttributeValue.option),
    ).where(Product.is_deleted.is_(False))


async def _load_dictionary(db) -> AttributeDictionary:
    """从数据库加载属性词典（失败时退回空词典：绝不猜、不放宽）。"""
    try:
        return await await_load_dictionary(db)
    except Exception:  # noqa: BLE001 - 词典不可用时保持 fail-closed
        return EMPTY_DICTIONARY


def _build_product_search_statement(
    params: ProductSearchInput,
    dictionary: AttributeDictionary,
    *,
    tier: str = "exact",
):
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

    # 数值条件：受治理属性优先，其次回落到产品既有列
    for numeric in params.numeric_filters:
        stmt = stmt.where(_numeric_predicate(numeric, dictionary))

    # 属性硬条件（不同属性 AND；属性缺失不算命中）
    for facet in params.hard_facets:
        if facet.attribute_code == "category":
            stmt = stmt.where(_category_predicate(facet))
        else:
            stmt = stmt.where(_attribute_predicate(facet))

    # 否定条件（"不要黑色"/"排除圆形"）
    for facet in params.exclude_values:
        if facet.attribute_code == "category":
            continue
        # _attribute_predicate 已内建 negated 语义，这里不能再次取反
        stmt = stmt.where(_attribute_predicate(facet, negated=True))

    stmt = _apply_ordering(stmt, params, tier=tier)
    return stmt.limit(min(params.limit, 100))


# ---------------------------------------------------------------------------
# 属性硬条件 SQL
# ---------------------------------------------------------------------------


def _attribute_predicate(facet: HardFacet, *, negated: bool = False):
    """产品必须（或不得）拥有该属性的指定取值。

    * 无 option_id 的 text/number 属性按 value_text / value_num 匹配；
    * 属性完全缺失 -> 不满足（IN 语义天然排除）；
    * match_mode='all' 要求同一属性多个取值全部满足。
    """
    pav = aliased(ProductAttributeValue)
    cad = aliased(CatalogAttributeDefinition)
    cao = aliased(CatalogAttributeOption)

    base = (
        select(pav.product_id)
        .select_from(pav)
        .join(cad, cad.id == pav.attribute_id)
        .outerjoin(cao, cao.id == pav.option_id)
        .where(
            cad.code == facet.attribute_code,
            cad.is_deleted.is_(False),
            pav.is_deleted.is_(False),
        )
    )
    if facet.values:
        if facet.match_mode == "all":
            # 同一属性多个取值全部满足：按 product 分组计数
            counted = (
                select(pav.product_id.label("pid"))
                .select_from(pav)
                .join(cad, cad.id == pav.attribute_id)
                .join(cao, cao.id == pav.option_id)
                .where(
                    cad.code == facet.attribute_code,
                    cad.is_deleted.is_(False),
                    cao.is_deleted.is_(False),
                    pav.is_deleted.is_(False),
                    cao.code.in_(facet.values),
                )
                .group_by(pav.product_id)
                .having(func.count(func.distinct(cao.code)) >= len(facet.values))
            ).subquery()
            predicate = Product.id.in_(select(counted.c.pid))
        else:
            base = base.where(cao.code.in_(facet.values), cao.is_deleted.is_(False))
            predicate = Product.id.in_(select(base.subquery().c.product_id))
    else:
        predicate = Product.id.in_(select(base.subquery().c.product_id))

    return ~predicate if negated else predicate


def _category_predicate(facet: HardFacet):
    """category 仍走现有 Category 树（含子孙类目），不另建产品分类表。"""
    names = {normalize_text(v) for v in facet.values if v}
    if not names:
        return and_(True)
    seed = (
        select(Category.id.label("id"), Category.parent_id.label("parent_id"))
        .where(
            Category.is_deleted.is_(False),
            Category.category_name.isnot(None),
            func.lower(func.trim(Category.category_name)).in_(list(names)),
        )
        .cte(name="category_tree", recursive=True)
    )
    descendants = (
        select(Category.id, Category.parent_id)
        .join(seed, Category.parent_id == seed.c.id)
        .where(Category.is_deleted.is_(False))
    )
    tree = seed.union(descendants)
    return Product.category_id.in_(select(tree.c.id))


def _spec_part_expr(position: int):
    """从 ``specification``（形如 ``3200*1620*760``）取第 N 段的数值。

    用可移植的字符串运算实现，避免依赖 Postgres 专有的 ``split_part``，
    使同一段 SQL 既能在 PG 上跑，也能在单测的 SQLite 上跑。
    """
    column = Product.specification
    if position == 1:
        segment = func.substr(column, 1, func.instr(column, "*") - 1)
    elif position == 2:
        rest = func.substr(column, func.instr(column, "*") + 1)
        segment = func.substr(rest, 1, func.instr(rest, "*") - 1)
    else:
        rest = func.substr(column, func.instr(column, "*") + 1)
        rest = func.substr(rest, func.instr(rest, "*") + 1)
        segment = rest
    return func.cast(
        func.nullif(func.trim(func.replace(segment, "*", "")), ""), Float
    )


_NUMERIC_PRODUCT_COLUMNS = {
    "face_price": Product.face_price,
    "specification_length_mm": _spec_part_expr(1),
    "specification_width_mm": _spec_part_expr(2),
    "specification_height_mm": _spec_part_expr(3),
}


def _numeric_predicate(numeric: NumericFilter, dictionary: AttributeDictionary):
    """数值条件：优先受治理属性，其次产品既有列。"""
    definition = dictionary.definitions.get(numeric.attribute_code)
    governed = definition is not None and definition.data_type in ("number", "range")
    if governed and numeric.attribute_code not in _NUMERIC_PRODUCT_COLUMNS:
        pav = aliased(ProductAttributeValue)
        cad = aliased(CatalogAttributeDefinition)
        base = (
            select(pav.product_id)
            .select_from(pav)
            .join(cad, cad.id == pav.attribute_id)
            .where(
                cad.code == numeric.attribute_code,
                cad.is_deleted.is_(False),
                pav.is_deleted.is_(False),
                pav.value_num.isnot(None),
            )
        )
        if numeric.min_value is not None:
            base = base.where(pav.value_num >= numeric.min_value)
        if numeric.max_value is not None:
            base = base.where(pav.value_num <= numeric.max_value)
        return Product.id.in_(select(base.c.product_id))

    column = _NUMERIC_PRODUCT_COLUMNS.get(numeric.attribute_code)
    if column is None:
        return and_(True)
    predicates = []
    if numeric.min_value is not None:
        predicates.append(column >= numeric.min_value)
    if numeric.max_value is not None:
        predicates.append(column <= numeric.max_value)
    return and_(*predicates) if predicates else and_(True)


# ---------------------------------------------------------------------------
# 排序：不进 limit 之前错误截断候选
# ---------------------------------------------------------------------------


def _apply_ordering(stmt, params: ProductSearchInput, *, tier: str):
    """结构化查询的排序。

    先在 SQL 内完成排序（含规格长度），再 limit，避免"只在前 20 行里排"。
    用户明确指定的排序作为 override 优先。
    """
    sort_by = params.sort_by or (
        "face_price" if tier == "exact" and params.match_tier == "exact" else None
    )
    if sort_by == "face_price":
        direction = (
            Product.face_price.desc() if params.sort_order == "desc" else Product.face_price.asc()
        )
        return stmt.order_by(
            case((Product.face_price == 99999, 1), else_=0), direction, Product.id
        )
    if sort_by in ("specification_length_mm", "specification_length"):
        column = _NUMERIC_PRODUCT_COLUMNS["specification_length_mm"]
        direction = column.desc() if params.sort_order == "desc" else column.asc()
        # 无规格的产品排最后，不影响有规格者的次序
        return stmt.order_by(
            case((column.is_(None), 1), else_=0), direction, Product.id
        )
    # 默认：active 优先、有图优先、资料完整优先，再按创建时间
    return stmt.order_by(
        case((Product.status == "active", 0), else_=1),
        case((Product.images.any(), 0), else_=1),
        case((Product.completeness_status == "complete", 0), else_=1),
        Product.create_time.desc(),
        Product.id,
    )


async def _text_recall(db, soft_terms: list[str], limit: int) -> list[Product]:
    """自由文本召回：pg_trgm 相似度排序（缺失扩展时回退 ILIKE）。

    只补充软词命中，绝不冒充属性精确命中。
    """
    if not soft_terms:
        return []
    stmt = _base_product_stmt()
    conditions = [_search_term(term) for term in soft_terms]
    if conditions:
        stmt = stmt.where(or_(*conditions))
    stmt = stmt.order_by(Product.create_time.desc()).limit(limit)
    try:
        rows = (await db.execute(stmt)).scalars().all()
    except Exception:  # noqa: BLE001 - 文本召回失败不应让整次查询失败
        return []
    return list(rows)


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


def _product_payload(
    products: list[Product],
    current_user: dict[str, Any],
    *,
    match_tier: str | None = None,
    params: ProductSearchInput | None = None,
    dictionary: AttributeDictionary | None = None,
) -> dict[str, Any]:
    dictionary = dictionary or EMPTY_DICTIONARY
    now = datetime.now(UTC)
    cards: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for p in products:
        sid = f"db_product_{p.id}"
        card = _product_card(p, current_user)
        attributes = _attribute_summary(p, dictionary)
        card["attributes"] = attributes
        matched, reasons = _match_report(p, params, dictionary)
        card["matched_facets"] = matched
        card["match_reason"] = reasons
        if match_tier:
            card["match_tier"] = match_tier
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
    payload: dict[str, Any] = {
        "products": cards,
        "facts": facts,
        "sources": sources,
    }
    if match_tier:
        payload["match_tier"] = match_tier
    if params is not None:
        payload["relaxed_conditions"] = []
        payload["unknown_terms"] = list(params.unknown_terms) if params.unknown_terms else []
        payload["matched_facets"] = [
            f.attribute_code for f in params.hard_facets
        ]
    return payload


def _attribute_summary(p: Product, dictionary: AttributeDictionary) -> dict[str, Any]:
    """产品受治理属性快照（option code + label）。"""
    out: dict[str, Any] = {}
    for value in getattr(p, "attribute_values", []) or []:
        view = dictionary.view_by_id(value.attribute_id)
        if view is None:
            continue
        entry: dict[str, Any] = {
            "attribute_code": view.code,
            "attribute_name": view.name,
        }
        if value.option is not None:
            entry["option_code"] = value.option.code
            entry["label"] = value.option.label
        elif value.value_text is not None:
            entry["value_text"] = value.value_text
        elif value.value_num is not None:
            entry["value_num"] = value.value_num
            entry["unit"] = value.unit
        entry["verified"] = bool(value.verified)
        out.setdefault(view.code, []).append(entry)
    return out


def _match_report(
    p: Product, params: ProductSearchInput | None, dictionary: AttributeDictionary
) -> tuple[list[str], str]:
    if params is None:
        return [], ""
    values = {v.attribute_id: v for v in getattr(p, "attribute_values", []) or []}
    code_by_option: dict = {}
    for value in values.values():
        if value.option is not None:
            code_by_option[str(value.option.id)] = value.option.code
    option_codes = set(code_by_option.values())
    matched: list[str] = []
    missing: list[str] = []
    for facet in params.hard_facets:
        if facet.attribute_code == "category":
            matched.append("category")
            continue
        if facet.values:
            if any(v in option_codes for v in facet.values):
                matched.append(facet.attribute_code)
            else:
                missing.append(facet.attribute_code)
        else:
            matched.append(facet.attribute_code)
    if matched and not missing:
        return matched, "满足全部显式属性硬条件"
    if matched and missing:
        return matched, f"部分属性命中，未满足: {'、'.join(missing)}"
    return [], "未满足显式属性硬条件"


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
            token_type="file_content",
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
        "material_description": p.material_description,
        "stock_status": p.stock_status,
        "stock_status_display": "库存待确认" if p.stock_status == "unknown" else p.stock_status,
        "status": p.status,
        "completeness_status": p.completeness_status,
        "specification": p.specification,
        "specification_length_mm": _specification_length_mm(p.specification),
        "colors": p.colors,
        "delivery_period": p.delivery_period,
        "description": p.description,
        "tags": [
            tag.tag_name
            for tag in getattr(p, "tags", [])
            if not getattr(tag, "is_deleted", False)
        ],
        "cover_image_url": cover_image_url,
    }
