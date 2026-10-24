from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge.attributes import (
    EMPTY_DICTIONARY,
    AttributeDictionary,
    build_product_query,
)
from app.knowledge.entities import QueryEntities
from app.knowledge.facets import ProductFacets
from app.knowledge.intent import KnowledgeIntent
from app.knowledge.schemas import KnowledgeQueryRequest

UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
# 型号：允许 P-104300001 / EN74-2.320162 / EMD70.095095 等。
# 结尾用"非型号字符"前瞻而不是 \b：中文与数字之间不构成 \b 边界。
PRODUCT_NO_RE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*(?:[-._/][A-Za-z0-9]+)*(?![A-Za-z0-9._/-])"
)
PRICE_RE = re.compile(
    r"(?:(\d+(?:\.\d+)?)\s*(?:元|块|rmb|RMB)|(?:预算|价格|面价)\s*(?:为|是|不超过|低于|以内)?\s*(\d+(?:\.\d+)?))",
    re.IGNORECASE,
)
SECURITY_TERMS = (
    "sql",
    "select ",
    "drop ",
    "delete ",
    "shell",
    "curl",
    "http://",
    "https://",
    "执行",
    "改库",
    "写入数据库",
    "忽略权限",
    "系统提示词",
    "api_key",
    "jwt_secret",
    "连接字符串",
    "输出所有用户的密码",
)
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
BUSINESS_TERMS = (
    "铭达",
    "圣奥",
    "办公桌",
    "班台",
    "总裁桌",
    "会议桌",
    "办公椅",
    "背柜",
)


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: KnowledgeIntent
    entities: QueryEntities = Field(default_factory=QueryEntities)
    required_tools: list[str] = Field(default_factory=list)
    tool_params: dict[str, dict] = Field(default_factory=dict)
    retrieval: dict = Field(default_factory=lambda: {"enabled": False, "topics": []})
    answer_mode: str = "direct"
    proposed_action: None = None


@runtime_checkable
class Planner(Protocol):
    def plan(self, request: KnowledgeQueryRequest) -> QueryPlan: ...


class RuleBasedPlanner:
    """规则规划器。

    词典由调用方注入（``set_dictionary``）；缺词典时不会回退到硬编码词表，
    也不会把整句中文拼成一个必然无法命中的关键词。
    """

    def __init__(self, dictionary: AttributeDictionary | None = None) -> None:
        self._dictionary = dictionary or EMPTY_DICTIONARY

    def set_dictionary(self, dictionary: AttributeDictionary) -> None:
        self._dictionary = dictionary

    @property
    def dictionary(self) -> AttributeDictionary:
        return self._dictionary

    def plan(self, request: KnowledgeQueryRequest) -> QueryPlan:
        msg = request.message.strip()
        lower = msg.lower()
        if any(term in lower for term in SECURITY_TERMS):
            return QueryPlan(intent=KnowledgeIntent.UNSUPPORTED, answer_mode="refusal")

        entities = QueryEntities()
        entities.product_ids = [str(x) for x in request.scope.product_ids] + UUID_RE.findall(
            msg
        )
        entities.product_nos = _extract_product_nos(msg)
        entities.status_terms = [code for term, code in QUALITY_TERMS.items() if term in msg]

        query = build_product_query(
            msg,
            self._dictionary,
            product_nos=entities.product_nos,
            product_ids=entities.product_ids,
        )
        entities.query = query
        entities.facets = ProductFacets.from_query(query)
        entities.keywords = list(query.soft_terms)

        # 数值条件同时回写到兼容字段（旧调用点与既有测试仍可用）
        for numeric in query.numeric_filters:
            if numeric.attribute_code == "face_price":
                if numeric.min_value is not None:
                    entities.price_min = numeric.min_value
                if numeric.max_value is not None:
                    entities.price_max = numeric.max_value
        entities.price_sort = query.sort_order if query.sort == "face_price" else None
        entities.specification_sort = (
            query.sort_order if query.sort == "specification_length_mm" else None
        )

        if any(x in msg for x in ("采购", "供应商", "交期", "供货", "供应")) and any(
            x in msg for x in ("比较", "对比", "哪个", "选择")
        ):
            return QueryPlan(
                intent=KnowledgeIntent.PROCUREMENT_COMPARE,
                entities=entities,
                required_tools=["supplier.compare"],
                answer_mode="procurement",
            )
        if any(x in msg for x in ("创建方案", "生成方案", "方案草稿", "加入方案", "方案篮")):
            return QueryPlan(
                intent=KnowledgeIntent.PROPOSAL_DRAFT,
                entities=entities,
                required_tools=[
                    "product.get_many"
                    if (entities.product_ids or entities.product_nos)
                    else "product.search"
                ],
                answer_mode="action_proposal_draft",
            )
        if query.has_constraints():
            return QueryPlan(
                intent=KnowledgeIntent.PRODUCT_SEARCH,
                entities=entities,
                required_tools=["product.search"],
                # 有显式硬条件时只信结构化精确过滤；语义召回只作为软补充。
                retrieval={
                    "enabled": not bool(query.hard_facets),
                    "topics": entities.keywords[:5],
                },
                answer_mode="search",
            )
        if any(x in msg for x in ("比较", "哪个更适合", "区别", "差别")):
            return QueryPlan(
                intent=KnowledgeIntent.PRODUCT_COMPARE,
                entities=entities,
                required_tools=["product.get_many", "product.compare"],
                retrieval={"enabled": True, "topics": entities.keywords[:5]},
                answer_mode="comparison",
            )
        if any(
            x in msg
            for x in ("缺什么", "哪些产品待核价", "待完善", "质量", "缺图", "缺说明书", "库存未知")
        ):
            tool = (
                "quality.list_issues"
                if ("哪些" in msg or "列表" in msg or "产品" in msg)
                else "quality.summary"
            )
            return QueryPlan(
                intent=KnowledgeIntent.QUALITY_LIST_ISSUES
                if tool.endswith("list_issues")
                else KnowledgeIntent.QUALITY_SUMMARY,
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
        knowledge_terms = (
            "怎么", "如何", "怎样", "说明书", "安装", "维护", "资料", "配置", "空间利用率"
        )
        if any(term in msg for term in knowledge_terms):
            return QueryPlan(
                intent=KnowledgeIntent.KNOWLEDGE_QUESTION,
                entities=entities,
                required_tools=[],
                retrieval={"enabled": True, "topics": entities.keywords[:5]},
                answer_mode="knowledge",
            )
        return QueryPlan(
            intent=(
                KnowledgeIntent.PRODUCT_SEARCH
                if entities.keywords
                else KnowledgeIntent.KNOWLEDGE_QUESTION
            ),
            entities=entities,
            required_tools=["product.search"] if entities.keywords else [],
            retrieval={"enabled": True, "topics": entities.keywords[:5]},
            answer_mode="search" if entities.keywords else "knowledge",
        )


def _extract_product_nos(message: str) -> list[str]:
    candidates = PRODUCT_NO_RE.findall(message)
    blocked = {"RMB", "SQL", "http", "https"}
    out: list[str] = []
    for item in candidates:
        if item in blocked or item.isdigit() or len(item) < 3:
            continue
        if item not in out:
            out.append(item)
    return out[:20]


def get_planner() -> Planner:
    return RuleBasedPlanner()
