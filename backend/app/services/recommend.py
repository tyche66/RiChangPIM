import json
import re
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import AIServiceAdapter
from app.core.serializers import filter_sensitive_fields
from app.models.product import Product, ProductTag
from app.schemas.ai import AIStatus, RecommendFilter

SYSTEM_PROMPT = (
    "你是 AI 选品助手。基于用户模糊需求（预算/风格/场景/数量），"
    '输出严格 JSON：{"category_id": null|"UUID", "max_face_price": null|number>=0, '
    '"tag_ids": ["UUID", ...], "keywords": ["kw", ...], '
    '"stock_status": null|"in_stock"|"out_of_stock"|"preorder", '
    '"rationale": "<一句话>"}。严禁返回额外字段。'
)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    return json.loads(text)


class RecommendService:
    def __init__(self, adapter: AIServiceAdapter, db: AsyncSession, *, model: str):
        self.adapter = adapter
        self.db = db
        self.model = model

    async def recommend(
        self,
        requirement: str,
        current_user: dict[str, Any],
        *,
        limit: int = 20,
        role_code: str | None = None,
    ) -> dict:
        answer = ""
        try:
            resp = await self.adapter.chat(
                session_id="recommend",
                message=requirement,
                history=[{"role": "system", "content": SYSTEM_PROMPT}],
                stream=False,
            )
            answer = resp.get("answer", "")
        except Exception:
            return {
                "status": AIStatus.degraded.value,
                "filters_applied": {},
                "products": [],
                "rationale": "AI 服务不可用",
                "total": 0,
            }

        if not answer:
            return {
                "status": AIStatus.parse_failed.value,
                "filters_applied": {},
                "products": [],
                "rationale": "AI 未返回内容",
                "total": 0,
            }

        try:
            raw = _extract_json(answer)
        except (json.JSONDecodeError, AttributeError, ValueError):
            return {
                "status": AIStatus.parse_failed.value,
                "filters_applied": {},
                "products": [],
                "rationale": "AI 返回格式错误",
                "total": 0,
            }

        rationale = raw.get("rationale", "")
        if not isinstance(rationale, str):
            rationale = ""

        filter_raw = {k: v for k, v in raw.items() if k != "rationale"}
        try:
            filters_obj = RecommendFilter(**filter_raw)
        except ValidationError:
            return {
                "status": AIStatus.parse_failed.value,
                "filters_applied": {},
                "products": [],
                "rationale": "AI 返回字段校验失败",
                "total": 0,
            }

        stmt = select(Product).where(Product.is_deleted.is_(False))

        if filters_obj.category_id:
            stmt = stmt.where(Product.category_id == filters_obj.category_id)

        if filters_obj.max_face_price is not None:
            stmt = stmt.where(Product.face_price <= filters_obj.max_face_price)

        if filters_obj.tag_ids:
            stmt = (
                stmt.join(ProductTag, ProductTag.product_id == Product.id)
                .where(ProductTag.tag_id.in_(filters_obj.tag_ids))
                .distinct()
            )

        if filters_obj.keywords:
            from sqlalchemy import or_

            conditions = []
            for kw in filters_obj.keywords:
                conditions.append(Product.product_name.ilike(f"%{kw}%"))
                conditions.append(Product.description.ilike(f"%{kw}%"))
            stmt = stmt.where(or_(*conditions))

        if filters_obj.stock_status:
            stmt = stmt.where(Product.stock_status == filters_obj.stock_status.value)

        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        products = result.scalars().all()

        product_dicts: list[dict] = []
        for p in products:
            d = {
                "id": str(p.id),
                "product_no": p.product_no,
                "product_name": p.product_name,
                "brand_id": str(p.brand_id),
                "category_id": str(p.category_id),
                "face_price": p.face_price,
                "cost_price": p.cost_price,
                "supplier_id": str(p.supplier_id),
                "material": p.material,
                "stock_status": p.stock_status,
                "description": p.description,
                "_verified": True,
                "_verified_by": "business_api",
            }
            d = filter_sensitive_fields(d, role_code)
            product_dicts.append(d)

        filters_applied: dict[str, Any] = {
            "category_id": str(filters_obj.category_id) if filters_obj.category_id else None,
            "max_face_price": filters_obj.max_face_price,
            "tag_ids": [str(t) for t in filters_obj.tag_ids],
            "keywords": list(filters_obj.keywords),
            "stock_status": filters_obj.stock_status.value if filters_obj.stock_status else None,
        }

        return {
            "status": AIStatus.success.value,
            "filters_applied": filters_applied,
            "products": product_dicts,
            "rationale": rationale,
            "total": len(product_dicts),
        }
