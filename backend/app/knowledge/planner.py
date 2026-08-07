from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge.entities import QueryEntities
from app.knowledge.intent import KnowledgeIntent
from app.knowledge.schemas import KnowledgeQueryRequest

UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
PRODUCT_NO_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9./_-]{2,63}\b")
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
KEYWORD_STOP_TERMS = (
    "找出",
    "找一下",
    "帮我找",
    "推荐",
    "最便宜",
    "便宜",
    "最低价",
    "价格最低",
    "最长",
    "最短",
    "的",
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
        prices = [
            float(value)
            for match in PRICE_RE.findall(msg)
            for value in match
            if value and float(value) != 99999
        ]
        if prices:
            entities.price_max = max(prices)
            price_tokens = {
                str(int(price)) if price.is_integer() else str(price) for price in prices
            }
            entities.keywords = [
                keyword for keyword in entities.keywords if keyword not in price_tokens
            ]
        if any(x in msg for x in ("最便宜", "最低价", "价格最低")):
            entities.price_sort = "asc"
        if any(x in msg for x in ("最贵", "最高价", "价格最高")):
            entities.price_sort = "desc"
        if any(x in msg for x in ("最长", "最大尺寸", "尺寸最大")):
            entities.specification_sort = "desc"
        if any(x in msg for x in ("最短", "最小尺寸", "尺寸最小")):
            entities.specification_sort = "asc"

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
        if any(x in msg for x in ("怎么", "如何", "说明书", "安装", "维护", "资料")):
            return QueryPlan(
                intent=KnowledgeIntent.KNOWLEDGE_QUESTION,
                entities=entities,
                required_tools=["product.search"] if entities.keywords else [],
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
        if item in blocked or item.isdigit():
            continue
        if item not in out:
            out.append(item)
    return out[:20]


def _keywords(message: str, product_nos: list[str]) -> list[str]:
    text = message
    for no in product_nos:
        text = text.replace(no, " ")
    for term in KEYWORD_STOP_TERMS:
        text = text.replace(term, " ")
    # Chinese natural-language questions are not safe database search terms.
    # Only retain explicit tokens and recognized product taxonomy terms here;
    # the complete question is sent to semantic retrieval separately.
    words = [w.strip(" ，。！？,.;：:") for w in re.split(r"\s+", text) if len(w.strip()) >= 2]
    out = [
        w
        for w in words
        if w not in {"比较", "哪个", "产品", "适合", "帮我", "一下"}
        and not re.search(r"[\u4e00-\u9fff]", w)
    ]
    # Also extract alphanumeric tokens from mixed Chinese/English text (e.g., "MT标签" -> "MT")
    mixed_tokens = re.findall(r"[A-Za-z0-9]{2,}", text)
    for token in mixed_tokens:
        if token not in out and token not in {"的", "产品", "有", "哪些"}:
            out.append(token)
    for term in BUSINESS_TERMS:
        if term in text and term not in out:
            out.append(term)
    compact = re.sub(r"[\s，。！？,.;：:]", "", text)
    if not out and re.fullmatch(r"[\u4e00-\u9fff]{2,12}", compact):
        out.append(compact)
    return out[:10]


def get_planner() -> Planner:
    return RuleBasedPlanner()
