from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge.entities import QueryEntities
from app.knowledge.intent import KnowledgeIntent
from app.knowledge.schemas import KnowledgeQueryRequest

UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
PRODUCT_NO_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9-]{2,31}\b")
PRICE_RE = re.compile(r"(?:(\d+(?:\.\d+)?)\s*(?:元|块|rmb|RMB|以内|以下|以下)?)")
SECURITY_TERMS = ("sql", "select ", "drop ", "delete ", "shell", "curl", "http://", "https://", "执行", "改库", "写入数据库")
QUALITY_TERMS = {
    "待核价": "face_price_status",
    "库存未知": "stock_unknown",
    "库存待确认": "stock_unknown",
    "草稿": "draft",
    "缺图": "missing_image",
    "缺说明书": "missing_manual",
    "资料待完善": "pending",
    "待完善": "pending",
}


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: KnowledgeIntent
    entities: QueryEntities = Field(default_factory=QueryEntities)
    required_tools: list[str] = Field(default_factory=list)
    retrieval: dict = Field(default_factory=lambda: {"enabled": False, "topics": []})
    answer_mode: str = "direct"
    proposed_action: None = None


@runtime_checkable
class Planner(Protocol):
    def plan(self, request: KnowledgeQueryRequest) -> QueryPlan: ...


class RuleBasedPlanner:
    def plan(self, request: KnowledgeQueryRequest) -> QueryPlan:
        msg = request.message.strip()
        lower = msg.lower()
        if any(term in lower for term in SECURITY_TERMS):
            return QueryPlan(intent=KnowledgeIntent.UNSUPPORTED, answer_mode="refusal")

        entities = QueryEntities()
        entities.product_ids = [str(x) for x in request.scope.product_ids] + UUID_RE.findall(msg)
        entities.product_nos = _extract_product_nos(msg)
        entities.status_terms = [code for term, code in QUALITY_TERMS.items() if term in msg]
        entities.keywords = _keywords(msg, entities.product_nos)
        prices = [float(x) for x in PRICE_RE.findall(msg) if float(x) != 99999]
        if prices:
            entities.price_max = max(prices)

        if any(x in msg for x in ("比较", "哪个更适合", "区别", "差别")):
            return QueryPlan(
                intent=KnowledgeIntent.PRODUCT_COMPARE,
                entities=entities,
                required_tools=["product.get_many", "product.compare"],
                retrieval={"enabled": True, "topics": entities.keywords[:5]},
                answer_mode="comparison",
            )
        if any(x in msg for x in ("缺什么", "哪些产品待核价", "待完善", "质量", "缺图", "缺说明书", "库存未知")):
            tool = "quality.list_issues" if ("哪些" in msg or "列表" in msg or "产品" in msg) else "quality.summary"
            return QueryPlan(
                intent=KnowledgeIntent.QUALITY_LIST_ISSUES if tool.endswith("list_issues") else KnowledgeIntent.QUALITY_SUMMARY,
                entities=entities,
                required_tools=[tool],
                answer_mode="quality",
            )
        if entities.product_ids or entities.product_nos:
            return QueryPlan(
                intent=KnowledgeIntent.PRODUCT_DETAIL,
                entities=entities,
                required_tools=["product.get_many"],
                retrieval={"enabled": True, "topics": entities.keywords[:5]},
                answer_mode="detail",
            )
        if any(x in msg for x in ("怎么", "如何", "说明书", "安装", "维护", "资料")):
            return QueryPlan(
                intent=KnowledgeIntent.KNOWLEDGE_QUESTION,
                entities=entities,
                required_tools=["product.search"],
                retrieval={"enabled": True, "topics": entities.keywords[:5]},
                answer_mode="knowledge",
            )
        return QueryPlan(
            intent=KnowledgeIntent.PRODUCT_SEARCH,
            entities=entities,
            required_tools=["product.search"],
            retrieval={"enabled": False, "topics": []},
            answer_mode="search",
        )


def _extract_product_nos(message: str) -> list[str]:
    candidates = PRODUCT_NO_RE.findall(message)
    blocked = {"RMB", "SQL", "http", "https"}
    out: list[str] = []
    for item in candidates:
        if item in blocked or item.isdigit():
            continue
        if item not in out:
            out.append(item)
    return out[:20]


def _keywords(message: str, product_nos: list[str]) -> list[str]:
    text = message
    for no in product_nos:
        text = text.replace(no, " ")
    words = [w.strip(" ，。！？,.;：:") for w in re.split(r"\s+", text) if len(w.strip()) >= 2]
    return [w for w in words if w not in {"比较", "哪个", "产品", "适合", "帮我", "一下"}][:10]


def get_planner() -> Planner:
    return RuleBasedPlanner()
