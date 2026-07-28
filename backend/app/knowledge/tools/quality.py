from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.knowledge.tools.base import ToolContext, ToolDefinition
from app.knowledge.tools.product import _product_card
from app.models.product import Product, ProductImage


class QualitySummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QualityListIssuesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issue_types: list[str] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=100)


class QualitySummaryTool:
    definition = ToolDefinition(
        name="quality.summary",
        version="1.0",
        description="统计质量问题",
        input_schema=QualitySummaryInput,
        required_permissions={"ai:quality", "stats:view"},
        risk_level="low",
        read_only=True,
        max_results=20,
        timeout_ms=1000,
        field_projection=True,
        audit_event="knowledge.tool.quality.summary",
    )

    async def run(self, params: QualitySummaryInput, context: ToolContext) -> dict[str, Any]:
        total = await _count(context, Product.is_deleted.is_(False))
        return {
            "facts": [
                {"name": "total_products", "value": total, "source_id": "db_quality_summary", "source_type": "database_fact"},
                {"name": "pending_price", "value": await _count(context, Product.face_price == 99999), "source_id": "db_quality_summary", "source_type": "database_fact"},
                {"name": "stock_unknown", "value": await _count(context, Product.stock_status == "unknown"), "source_id": "db_quality_summary", "source_type": "database_fact"},
                {"name": "draft_products", "value": await _count(context, Product.status == "draft"), "source_id": "db_quality_summary", "source_type": "database_fact"},
                {"name": "pending_completeness", "value": await _count(context, Product.completeness_status == "pending"), "source_id": "db_quality_summary", "source_type": "database_fact"},
            ],
            "sources": [{"source_id": "db_quality_summary", "source_type": "database_fact", "title": "产品质量规则统计", "access_policy": "role_projected"}],
        }


class QualityListIssuesTool:
    definition = ToolDefinition(
        name="quality.list_issues",
        version="1.0",
        description="待修复产品列表",
        input_schema=QualityListIssuesInput,
        required_permissions={"ai:quality", "product:view"},
        risk_level="low",
        read_only=True,
        max_results=100,
        timeout_ms=1000,
        field_projection=True,
        audit_event="knowledge.tool.quality.list_issues",
    )

    async def run(self, params: QualityListIssuesInput, context: ToolContext) -> dict[str, Any]:
        stmt = select(Product).options(
            selectinload(Product.brand),
            selectinload(Product.category),
            selectinload(Product.supplier),
            selectinload(Product.images).joinedload(ProductImage.attachment),
            selectinload(Product.manuals),
        ).where(Product.is_deleted.is_(False)).limit(params.limit)
        rows = (await context.db.execute(stmt)).scalars().all()
        issues: list[dict[str, Any]] = []
        products: list[dict[str, Any]] = []
        wanted = set(params.issue_types or [])
        for p in rows:
            product_issues = _issues_for(p)
            if wanted:
                product_issues = [i for i in product_issues if i["issue_type"] in wanted]
            if product_issues:
                issues.extend(product_issues)
                products.append(_product_card(p, context.current_user))
        return {"issues": issues[:100], "products": products[:100], "sources": [{"source_id": "db_quality_issues", "source_type": "database_fact", "title": "产品质量问题列表", "access_policy": "role_projected"}]}


async def _count(context: ToolContext, condition) -> int:
    result = await context.db.execute(select(func.count()).select_from(Product).where(Product.is_deleted.is_(False), condition))
    return int(result.scalar() or 0)


def _issues_for(p: Product) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if p.face_price == 99999:
        issues.append(_issue(p, "pending_price", "待核价"))
    if p.stock_status == "unknown":
        issues.append(_issue(p, "stock_unknown", "库存待确认"))
    if p.status == "draft":
        issues.append(_issue(p, "draft", "草稿产品"))
    if p.completeness_status == "pending":
        issues.append(_issue(p, "pending_completeness", "资料待完善"))
    if not getattr(p, "images", None):
        issues.append(_issue(p, "missing_image", "缺图"))
    if not getattr(p, "manuals", None):
        issues.append(_issue(p, "missing_manual", "缺说明书"))
    return issues


def _issue(p: Product, issue_type: str, label: str) -> dict[str, Any]:
    return {"product_id": str(p.id), "product_no": p.product_no, "product_name": p.product_name, "issue_type": issue_type, "label": label}
