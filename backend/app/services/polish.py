import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.base import AIServiceAdapter
from app.adapters.exceptions import AIAdapterError, AIAdapterInvalidResponseError
from app.models.sales import Proposal, ProposalItem
from app.schemas.ai import AIStatus, PolishRequest

SYSTEM_PROMPT = (
    "你是 AI-PIM 方案的润色助手。基于销售勾选的产品列表（包含名称、面价、参数），"
    '生成 JSON：{"summary": "<≤200字整体亮点>", "item_reasons": ["<≤60字/产品>", ...], '
    '"industry_phrases": ["<3条行业话术>", ...]}。严禁编造价格、库存或供应商。'
    '只返回 summary、item_reasons、industry_phrases 三个字段，不要包含客户信息、成本或供应商。'
)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


class PolishService:
    def __init__(self, adapter: AIServiceAdapter, db: AsyncSession, *, model: str):
        self.adapter = adapter
        self.db = db
        self.model = model

    async def polish_proposal(self, proposal_id: UUID, current_user: dict[str, Any]) -> dict:
        result = await self.db.execute(
            select(Proposal)
            .options(selectinload(Proposal.items).selectinload(ProposalItem.product))
            .where(Proposal.id == proposal_id)
        )
        proposal = result.scalar_one_or_none()
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        items_data: list[dict] = []
        for item in proposal.items:
            product = item.product
            if not product:
                continue
            d = {
                "product_name": product.product_name,
                "face_price": product.face_price,
                "material": getattr(product, "material", None),
                "description": getattr(product, "description", None),
                "quantity": item.quantity,
                "remark": item.remark,
            }
            items_data.append(d)

        prompt = (
            f"请为以下方案生成推荐话术：\n"
            f"方案名称：{proposal.proposal_name}\n"
            f"产品数量：{len(items_data)}\n"
            f"产品清单：\n{json.dumps(items_data, ensure_ascii=False, indent=2)}"
        )

        try:
            resp = await self.adapter.chat(
                session_id=str(proposal_id),
                message=prompt,
                history=[{"role": "system", "content": SYSTEM_PROMPT}],
                stream=False,
            )
        except AIAdapterError:
            raise
        except Exception as e:
            raise AIAdapterInvalidResponseError("AI 服务调用失败") from e
        answer = resp.get("answer", "")

        if not answer:
            raise AIAdapterInvalidResponseError("AI 未返回内容")

        parsed = _extract_json(answer)
        if not parsed:
            raise AIAdapterInvalidResponseError("AI 返回格式错误，无法解析")

        try:
            polish_data = PolishRequest(**parsed)
        except ValidationError as e:
            raise AIAdapterInvalidResponseError("AI 返回数据校验失败") from e

        if len(polish_data.item_reasons) != len(items_data):
            raise AIAdapterInvalidResponseError("AI 返回的产品理由数量不匹配")

        polish_content = json.dumps(
            {
                "summary": polish_data.summary,
                "item_reasons": polish_data.item_reasons,
                "industry_phrases": polish_data.industry_phrases,
            },
            ensure_ascii=False,
        )
        proposal.ai_polished = True
        proposal.ai_polish_content = polish_content
        proposal.ai_polish_at = datetime.now(UTC)
        proposal.ai_polish_model = self.model
        await self.db.commit()

        return {
            "status": AIStatus.success.value,
            "summary": polish_data.summary,
            "item_reasons": polish_data.item_reasons,
            "industry_phrases": polish_data.industry_phrases,
            "proposal_id": proposal_id,
            "polished_at": proposal.ai_polish_at,
        }
