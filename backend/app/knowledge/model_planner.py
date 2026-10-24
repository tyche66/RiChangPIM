from __future__ import annotations

import asyncio
import json
import logging
import unicodedata
from typing import Any

from sqlalchemy import select

from app.adapters.none import NoneAdapter
from app.core.config import settings
from app.knowledge.attributes import (
    EMPTY_DICTIONARY,
    AttributeDictionary,
    HardFacet,
    NumericFilter,
    ProductQuery,
    await_load_dictionary,
)
from app.knowledge.planner import Planner, QueryPlan
from app.knowledge.policy import ToolAuthorizationPolicy, get_tool_authorization_policy
from app.knowledge.schemas import KnowledgeQueryRequest
from app.models.product import Category

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 3


class ModelToolPlanner:
    """Lets the model select from a small, server-controlled set of read-only tools."""

    def __init__(
        self,
        fallback: Planner,
        registry,
        authz_policy: ToolAuthorizationPolicy | None = None,
    ) -> None:
        self.fallback = fallback
        self.registry = registry
        self.authz_policy = authz_policy or get_tool_authorization_policy()

    async def plan(
        self,
        request: KnowledgeQueryRequest,
        *,
        db,
        adapter,
        current_user: dict,
        permission_pool,
        session_id: str,
    ) -> QueryPlan:
        fallback = self.fallback.plan(request)
        if isinstance(adapter, NoneAdapter):
            return fallback

        allowed_tools = self._tools_for_user(permission_pool, current_user)
        if not allowed_tools:
            return fallback

        try:
            dictionary = await await_load_dictionary(db)
            categories = await _category_context(db)
            response = await asyncio.wait_for(
                adapter.chat(
                    session_id=session_id,
                    message=_planning_request(request.message),
                    history=[],
                    system=_planning_instructions(categories, allowed_tools, dictionary),
                    temperature=0,
                ),
                timeout=settings.AI_TOOL_PLANNING_TIMEOUT,
            )
            calls = _parse_tool_calls(response.get("answer"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("model_tool_planning_failed error_type=%s", type(exc).__name__)
            return fallback

        selected: list[str] = []
        params_by_tool: dict[str, dict] = {}
        for call in calls[:MAX_TOOL_CALLS]:
            name = call.get("name")
            arguments = call.get("arguments")
            if name not in allowed_tools:
                continue
            if not isinstance(arguments, dict) or name in params_by_tool:
                continue
            try:
                params_by_tool[name] = self.registry.validate_params(name, arguments)
            except Exception:  # noqa: BLE001
                continue
            selected.append(name)

        if not selected:
            return fallback
        if "product.search" in params_by_tool:
            model_params = params_by_tool["product.search"]
            # The model may omit entities that the deterministic parser already
            # extracted. Rule-derived hard constraints always win: the model can
            # only *add* dimensions the rules did not express, never relax them.
            rule_query = fallback.entities.query
            model_keywords = [
                _remove_explicit_facet_terms(keyword, rule_query)
                for keyword in model_params.get("keywords", [])
            ]
            model_params["keywords"] = list(
                dict.fromkeys(
                    fallback.entities.keywords + [keyword for keyword in model_keywords if keyword]
                )
            )
            model_params["keyword"] = (
                _remove_explicit_facet_terms(model_params.get("keyword"), rule_query) or None
            )
            model_params["product_nos"] = list(
                dict.fromkeys(
                    fallback.entities.product_nos + model_params.get("product_nos", [])
                )
            )
            model_params["product_ids"] = list(
                dict.fromkeys(
                    fallback.entities.product_ids + model_params.get("product_ids", [])
                )
            )
            rule_filters = dict(request.scope.filters)
            for numeric in rule_query.numeric_filters:
                if numeric.attribute_code == "face_price":
                    if numeric.min_value is not None:
                        rule_filters["face_price_min"] = numeric.min_value
                    if numeric.max_value is not None:
                        rule_filters["face_price_max"] = numeric.max_value
            model_filters = model_params.get("filters", {})
            if model_filters.get("keyword"):
                model_filters["keyword"] = _remove_explicit_facet_terms(
                    model_filters.get("keyword"), rule_query
                )
                if not model_filters["keyword"]:
                    model_filters.pop("keyword")
            model_params["filters"] = _merge_search_filters(rule_filters, model_filters)

            # 通用维度合并 + 属性字典校验：模型不得返回任意 attribute_code/option
            model_query = _sanitize_model_query(model_params, dictionary)
            rule_query.merge(model_query)
            merged = ProductQuery(
                hard_facets=[f.model_copy(deep=True) for f in rule_query.hard_facets],
                numeric_filters=[
                    f.model_copy(deep=True) for f in rule_query.numeric_filters
                ],
                exclude_values=[f.model_copy(deep=True) for f in rule_query.exclude_values],
                soft_terms=list(rule_query.soft_terms),
                unknown_terms=list(rule_query.unknown_terms),
                sort=rule_query.sort,
                sort_order=rule_query.sort_order,
                clarification_needed=rule_query.clarification_needed,
                alias_labels=dict(rule_query.alias_labels),
            )
            model_params["hard_facets"] = [
                f.model_dump(mode="json") for f in merged.hard_facets
            ]
            model_params["numeric_filters"] = [
                f.model_dump(mode="json") for f in merged.numeric_filters
            ]
            model_params["exclude_values"] = [
                f.model_dump(mode="json") for f in merged.exclude_values
            ]
            model_params["soft_terms"] = list(merged.soft_terms)
            model_params["unknown_terms"] = list(merged.unknown_terms)
            model_params["facets"] = {f.attribute_code: f.values for f in merged.hard_facets}
        elif fallback.entities.query.has_constraints() and "product.search" not in selected:
            # Do not let model tool selection bypass a deterministic hard facet.
            selected = ["product.search"]
            params_by_tool = {}
        return fallback.model_copy(
            update={
                "required_tools": selected,
                "tool_params": params_by_tool,
                "retrieval": {
                    "enabled": not fallback.entities.query.hard_facets,
                    "topics": fallback.entities.keywords[:5],
                },
            }
        )

    def _tools_for_user(self, permission_pool, current_user: dict) -> set[str]:
        tools: set[str] = set()
        for name in sorted(permission_pool.allowed_tools & self.registry.names()):
            definition = self.registry.definition(name)
            authz = self.authz_policy.authorize(
                name, permission_pool, current_user, definition.required_permissions
            )
            if not authz.allowed:
                continue
            tools.add(name)
        return tools


def _merge_search_filters(rule_filters: dict, model_filters: dict) -> dict:
    merged = {**model_filters, **rule_filters}
    for field, combine in (("face_price_min", max), ("face_price_max", min)):
        rule_value = rule_filters.get(field)
        model_value = model_filters.get(field)
        if rule_value is not None and model_value is not None:
            try:
                merged[field] = combine(float(rule_value), float(model_value))
            except (TypeError, ValueError):
                merged[field] = rule_value
    return merged


def _sanitize_model_query(
    model_params: dict, dictionary: AttributeDictionary
) -> ProductQuery:
    """把模型给出的 product.search 参数收敛成合法 ProductQuery。

    * ``attribute_code`` / option 必须存在于属性字典，否则丢弃；
    * 模型无法inescapable 覆盖规则：调用方随后以 rule 优先合并；
    * 未知但可能是属性的词进 ``unknown_terms``，不静默丢弃。
    """
    query = ProductQuery()
    known_codes = set(dictionary.definitions)

    raw_facets = model_params.get("hard_facets") or model_params.get("facets") or []
    if isinstance(raw_facets, dict):
        raw_facets = [
            {"attribute_code": code, "values": values}
            for code, values in raw_facets.items()
        ]
    for item in raw_facets:
        if not isinstance(item, dict):
            continue
        code = item.get("attribute_code")
        if code not in known_codes:
            continue
        values = [v for v in (item.get("values") or []) if v in dictionary.option_codes(code)]
        if not values:
            continue
        mode = item.get("match_mode") or "any"
        if mode not in ("any", "all"):
            mode = "any"
        query.hard_facets.append(
            HardFacet(
                attribute_code=code,
                values=values,
                required=True,
                match_mode=mode,
                source="model",
                confidence=float(item.get("confidence") or 0.0),
            )
        )

    for item in model_params.get("exclude_values") or []:
        if not isinstance(item, dict):
            continue
        code = item.get("attribute_code")
        if code not in known_codes:
            continue
        values = [v for v in (item.get("values") or []) if v in dictionary.option_codes(code)]
        if values:
            query.exclude_values.append(
                HardFacet(
                    attribute_code=code,
                    values=values,
                    required=False,
                    match_mode="any",
                    source="model",
                    confidence=float(item.get("confidence") or 0.0),
                )
            )

    raw_numeric = model_params.get("numeric_filters") or []
    if isinstance(raw_numeric, dict):
        # 兼容 {face_price: {min, max}} 形式
        raw_numeric = [
            {"attribute_code": code, **bounds} for code, bounds in raw_numeric.items()
        ]
    for item in raw_numeric:
        if not isinstance(item, dict):
            continue
        code = item.get("attribute_code")
        if code not in known_codes:
            continue
        try:
            numeric = NumericFilter(
                attribute_code=code,
                min_value=item.get("min_value"),
                max_value=item.get("max_value"),
                unit=item.get("unit"),
                source="model",
                confidence=float(item.get("confidence") or 0.0),
            )
        except (TypeError, ValueError):
            continue
        if not numeric.is_empty():
            query.numeric_filters.append(numeric)

    query.soft_terms = [t for t in (model_params.get("soft_terms") or []) if t]
    query.unknown_terms = [t for t in (model_params.get("unknown_terms") or []) if t]
    return query


def _remove_explicit_facet_terms(value: str, query: ProductQuery) -> str:
    """把已被规则解析出的属性词从模型给的自由文本里剔除。

    既剔除 option code，也剔除词典里该 option 的中文别名，避免模型把
    "弧形"重新塞回 keyword。
    """
    if not value:
        return ""
    remaining = unicodedata.normalize("NFKC", value)
    aliases: set[str] = set()
    for facet in query.hard_facets:
        for option in facet.values:
            aliases.add(option)
            for label in query.alias_labels.get(facet.attribute_code, {}).get(option, ()):
                aliases.add(label)
    for alias in sorted(aliases, key=len, reverse=True):
        if alias:
            remaining = remaining.replace(alias, " ")
    return " ".join(remaining.split())

async def _category_context(db) -> list[dict[str, Any]]:
    result = await db.execute(
        select(Category.category_name, Category.level)
        .where(Category.is_deleted.is_(False))
        .order_by(Category.level, Category.sort, Category.category_name)
        .limit(200)
    )
    return [dict(row._mapping) for row in result.all()]


def _parse_tool_calls(answer: str | None) -> list[dict[str, Any]]:
    text = (answer or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        calls = payload.get("tool_calls")
        if isinstance(calls, list):
            return [call for call in calls if isinstance(call, dict)]
    return []


def _planning_instructions(
    categories: list[dict[str, Any]],
    allowed_tools: set[str],
    dictionary: AttributeDictionary | None = None,
) -> str:
    dictionary = dictionary or EMPTY_DICTIONARY
    attribute_lines: list[str] = []
    for code, view in sorted(dictionary.definitions.items()):
        if not view.searchable:
            continue
        options = ",".join(sorted(dictionary.option_codes(code)))
        attribute_lines.append(
            f"{code}[{view.data_type}]{'多值' if view.multi_value else ''}:{options}"
        )
    return (
        "你是 RiChangPIM 的只读工具规划器。理解用户完整自然语言，并选择查询所需的工具。"
        "仅输出合法 JSON，不要输出解释："
        "{\"tool_calls\":[{\"name\":\"工具名\",\"arguments\":{...}}]}。"
        "只能从可用工具选择，不能编造工具，不能执行写操作。用户要求最便宜时 sort_order 用 asc，"
        "最贵时用 desc；最长时 sort_by 用 specification_length 且 sort_order 用 desc；"
        "最短时 sort_order 用 asc。当前产品、价格、库存和规格问题使用 product.search。"
        "product.search 参数：keywords(string数组)、product_nos(string数组)、filters(object)、"
        "hard_facets(array，每项 {attribute_code, values[], match_mode:any|all})、"
        "numeric_filters(array，每项 {attribute_code, min_value, max_value})、"
        "exclude_values(array，用户明确否定的条件)、"
        "soft_terms(string数组)、unknown_terms(string数组)。"
        "不同属性之间必须同时满足（AND）；同一属性的多个同义词取 any。"
        "只能使用下列已定义的属性与取值，不得编造 attribute_code 或 option；"
        "无法归一的词放入 unknown_terms，不得拼成一个整体关键词。"
        f"\n已定义属性（code[类型]多值?:取值）：{attribute_lines}"
        "sort_by(face_price 或 specification_length)、sort_order(asc 或 desc)、limit(1-100)。"
        "product.get_many/product.compare 参数：product_ids(string数组) "
        "或 product_nos(string数组)。"
        "quality.summary 无参数；quality.list_issues 参数：issue_types(string数组)、limit(1-50)。"
        "supplier.compare 参数：product_ids(string数组) 或 product_nos(string数组)。"
        f"\n可用工具：{sorted(allowed_tools)}"
        f"\n可见品类（name 和 level）：{categories}"
    )


def _planning_request(message: str) -> str:
    return (
        "不要回答下列用户请求。只输出工具计划 JSON，格式为 "
        '{"tool_calls":[{"name":"工具名","arguments":{...}}]}。'
        f"\n待处理用户请求：{message}"
    )
