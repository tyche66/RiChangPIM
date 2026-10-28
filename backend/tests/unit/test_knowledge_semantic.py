"""自然语言语义筛选层（app/knowledge/semantic.py）单测。

覆盖三类风险：
1. 模型输出解析容错（代码围栏 / 前后杂讯）；
2. **fail-closed**：编造的产品编号、不适配器、超时/异常都不得让脏数据进结果，
   也不得让整次查询失败；
3. 负向场景必须保持为空——「巴洛克式会议桌」这类确实没有的查询不能硬凑。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.none import NoneAdapter
from app.knowledge.attributes import (
    AliasEntry,
    AttributeDefinitionView,
    AttributeDictionary,
)
from app.knowledge.gateway import KnowledgeGateway
from app.knowledge.model_planner import _planning_instructions
from app.knowledge.planner import QueryPlan
from app.knowledge.schemas import KnowledgeQueryRequest
from app.knowledge.semantic import (
    MAX_SCREEN_CANDIDATES,
    attribute_context_lines,
    resolve_facets,
    screen_products,
)


def _adapter(answer: str) -> MagicMock:
    adapter = MagicMock()
    adapter.chat = AsyncMock(return_value={"answer": answer})
    return adapter


def _candidate(product_no: str, **extra) -> dict:
    card = {
        "id": f"id-{product_no}",
        "product_no": product_no,
        "product_name": f"{product_no} 名称",
        "category_name": "会议桌",
        "brand_name": "圣奥",
        "tags": ["灵多"],
        "attributes": {"style": ["modern"], "shape": ["rect"]},
        "colors": ["grey"],
        "material": "板材",
        "description": "现代简约职员桌",
    }
    card.update(extra)
    return card


class TestModelNumberExtraction:
    """型号提取：纯英文词必须被当成属性词/普通词，不能变成 product_no。

    2026-10-28 实测：查询「modern」被解析成 ``product_nos=['modern']``，
    ``product_no IN ('modern')`` 把 style=modern 的 175 款产品过滤成 0。
    """

    def _dictionary(self) -> AttributeDictionary:
        definitions = {
            "style": AttributeDefinitionView(
                code="style", name="风格", data_type="option",
                multi_value=False, searchable=True, hard_filterable=True,
            ),
            "series": AttributeDefinitionView(
                code="series", name="系列", data_type="option",
                multi_value=False, searchable=True, hard_filterable=True,
            ),
        }
        aliases = [
            AliasEntry(
                attribute_code="style", option_code="modern",
                alias="modern", normalized="modern",
            ),
            AliasEntry(
                attribute_code="series", option_code="灵多",
                alias="LIDO", normalized="lido",
            ),
        ]
        return AttributeDictionary(definitions=definitions, aliases=aliases)

    def test_real_model_numbers_survive(self):
        from app.knowledge.planner import _extract_product_nos

        nos = _extract_product_nos("EN74-2.320162 和 P-104300001", set())
        assert "EN74-2.320162" in nos
        assert "P-104300001" in nos

    def test_pure_english_word_is_not_a_model_number(self):
        from app.knowledge.planner import _extract_product_nos

        assert _extract_product_nos("modern", set()) == []
        assert _extract_product_nos("MODERN 风格", set()) == []

    def test_dictionary_alias_is_not_a_model_number(self):
        from app.knowledge.planner import _extract_product_nos

        # 即便含分隔符，撞上词典别名也按属性词处理
        assert _extract_product_nos("LIDO 桌子", {"lido"}) == []

    def test_looks_like_model_number_shape(self):
        from app.knowledge.planner import looks_like_model_number

        assert looks_like_model_number("P-104300001") is True
        assert looks_like_model_number("EMD70.095095") is True
        assert looks_like_model_number("CHT68SW") is True
        assert looks_like_model_number("modern") is False
        assert looks_like_model_number("ab") is False

    def test_planner_entities_do_not_swallow_attribute_word(self):
        from app.knowledge.planner import RuleBasedPlanner

        planner = RuleBasedPlanner(self._dictionary())
        plan = planner.plan(KnowledgeQueryRequest(message="modern"))
        assert plan.entities.product_nos == []
        assert [f.attribute_code for f in plan.entities.query.hard_facets] == ["style"]
        assert plan.entities.query.hard_facets[0].values == ["modern"]


class TestResolveFacets:
    """语义归一：自然语言 -> 受治理取值；编造的属性/取值必须被丢弃。"""

    def _dictionary(self) -> AttributeDictionary:
        return _test_dictionary()

    def test_natural_phrasing_resolves_to_governed_option(self):
        adapter = _adapter(
            '{"facets":[{"attribute_code":"style","values":["modern"]}],'
            '"interpretation":"年轻时尚对应现代风格"}'
        )
        result = asyncio.run(
            resolve_facets("年轻时尚不老气的办公桌", self._dictionary(),
                           adapter=adapter, session_id="s")
        )
        assert result.used is True
        assert [f.attribute_code for f in result.facets] == ["style"]
        assert result.facets[0].values == ["modern"]
        assert result.facets[0].source == "model"
        assert result.interpretation == "年轻时尚对应现代风格"

    def test_unknown_attribute_is_dropped(self):
        adapter = _adapter(
            '{"facets":[{"attribute_code":"mood","values":["chill"]},'
            '{"attribute_code":"style","values":["modern"]}]}'
        )
        result = asyncio.run(
            resolve_facets("chill 的桌子", self._dictionary(),
                           adapter=adapter, session_id="s")
        )
        assert [f.attribute_code for f in result.facets] == ["style"]

    def test_unknown_option_is_dropped(self):
        adapter = _adapter('{"facets":[{"attribute_code":"style","values":["baroque"]}]}')
        result = asyncio.run(
            resolve_facets("巴洛克", self._dictionary(), adapter=adapter, session_id="s")
        )
        assert result.facets == ()
        assert result.used is False

    def test_non_option_attribute_is_not_accepted(self):
        """number 型属性不能走 option facet。"""
        adapter = _adapter('{"facets":[{"attribute_code":"face_price","values":["cheap"]}]}')
        result = asyncio.run(
            resolve_facets("便宜点", self._dictionary(), adapter=adapter, session_id="s")
        )
        assert result.facets == ()

    def test_empty_facets_means_no_match(self):
        adapter = _adapter('{"facets":[],"interpretation":"无法归一"}')
        result = asyncio.run(
            resolve_facets("嗯", self._dictionary(), adapter=adapter, session_id="s")
        )
        assert result.used is False

    def test_none_adapter_and_empty_message_short_circuit(self):
        adapter = _adapter("nope")
        assert asyncio.run(
            resolve_facets("现代风格", self._dictionary(),
                           adapter=NoneAdapter(), session_id="s")
        ).used is False
        assert asyncio.run(
            resolve_facets("", self._dictionary(), adapter=adapter, session_id="s")
        ).used is False
        adapter.chat.assert_not_awaited()

    def test_adapter_failure_fails_closed(self):
        adapter = MagicMock()
        adapter.chat = AsyncMock(side_effect=RuntimeError("boom"))
        result = asyncio.run(
            resolve_facets("现代风格", self._dictionary(), adapter=adapter, session_id="s")
        )
        assert result.facets == ()

    def test_prompt_carries_chinese_aliases(self):
        adapter = _adapter('{"facets":[]}')
        asyncio.run(
            resolve_facets("现代风格", self._dictionary(), adapter=adapter, session_id="s")
        )
        message = adapter.chat.await_args.kwargs["message"]
        assert "现代风格" in message
        assert "style(风格)" in message


class TestRecoverProducts:
    """网关兜底链路：语义归一优先于语义筛选；负向必须保持空。"""

    def _gateway(self, adapter, planner=None) -> KnowledgeGateway:
        gateway = KnowledgeGateway.__new__(KnowledgeGateway)
        gateway.adapter = adapter
        gateway.planner = planner or _FakePlanner()
        return gateway

    def _request(self, message: str) -> KnowledgeQueryRequest:
        return KnowledgeQueryRequest(message=message)

    def test_semantic_facets_beat_screening(self):
        resolve = _adapter(
            '{"facets":[{"attribute_code":"style","values":["modern"]}],'
            '"interpretation":"理解为现代风格"}'
        )
        gateway = self._gateway(resolve)
        registry = MagicMock()
        registry.execute = AsyncMock(return_value={
            "products": [_candidate("P-1", match_tier="exact")],
            "relaxed_candidates": [],
            "text_candidates": [],
        })
        gateway.registry = registry
        plan = QueryPlan(intent="product_search", required_tools=["product.search"])
        tool_results = {"products": [], "candidates": [_candidate("P-9")]}
        out, note = asyncio.run(
            gateway._recover_products(
                self._request("年轻时尚不老气的办公桌"), plan, [],
                tool_results, MagicMock(), session_id="s",
            )
        )
        assert [c["product_no"] for c in out] == ["P-1"]
        assert note == "理解为现代风格"
        # 语义归一注入的硬条件要落到 plan 上，供确定答案/排序使用
        assert plan.entities.query.hard_facets
        assert plan.entities.query.hard_facets[0].values == ["modern"]
        # 整句关键词被剔除，否则会把结果过滤空
        sent = registry.execute.await_args.args[1]
        assert sent["keywords"] == []
        assert sent["keyword"] is None
        assert sent["hard_facets"][0]["attribute_code"] == "style"

    def test_falls_back_to_screening_when_facets_yield_nothing(self):
        # 同一个适配器先后被「语义归一」和「语义筛选」调用，返回不同 JSON
        adapter = MagicMock()
        adapter.chat = AsyncMock(side_effect=[
            {"answer": ('{"facets":[{"attribute_code":"style","values":["modern"]}],'
                        '"interpretation":"理解为现代风格"}')},
            {"answer": '{"selected":[{"product_no":"P-7","reason":"同为现代风格"}],'
                       '"interpretation":"要现代风格"}'},
        ])
        gateway = self._gateway(adapter)
        registry = MagicMock()
        registry.execute = AsyncMock(return_value={
            "products": [],
            "relaxed_candidates": [_candidate("P-7")],
            "text_candidates": [],
        })
        gateway.registry = registry
        plan = QueryPlan(intent="product_search", required_tools=["product.search"])
        tool_results = {"products": [], "candidates": []}
        out, note = asyncio.run(
            gateway._recover_products(
                self._request("现代风格的旧款班台"), plan, [],
                tool_results, MagicMock(), session_id="s",
            )
        )
        # P-7 来自归一后那次查询的宽松候选，再交给语义筛选
        assert [c["product_no"] for c in out] == ["P-7"]
        assert out[0]["match_tier"] == "semantic"

    def test_negative_query_stays_empty(self):
        resolve = _adapter('{"facets":[],"interpretation":"没有可归一的风格"}')
        gateway = self._gateway(resolve)
        registry = MagicMock()
        registry.execute = AsyncMock(return_value={
            "products": [], "relaxed_candidates": [], "text_candidates": [],
        })
        gateway.registry = registry
        plan = QueryPlan(intent="product_search", required_tools=["product.search"])
        tool_results = {"products": [], "candidates": []}
        out, note = asyncio.run(
            gateway._recover_products(
                self._request("巴洛克式会议桌"), plan, [],
                tool_results, MagicMock(), session_id="s",
            )
        )
        assert out == []
        assert note == "没有可归一的风格"

    def test_existing_products_short_circuit(self):
        adapter = _adapter('{"facets":[{"attribute_code":"style","values":["modern"]}]}')
        gateway = self._gateway(adapter)
        registry = MagicMock()
        registry.execute = AsyncMock(return_value={"products": [_candidate("P-1")]})
        gateway.registry = registry
        plan = QueryPlan(intent="product_search", required_tools=["product.search"])
        existing = [_candidate("P-1", match_tier="exact")]
        out, note = asyncio.run(
            gateway._recover_products(
                self._request("现代风格"), plan, existing, {"candidates": []},
                MagicMock(), session_id="s",
            )
        )
        assert out == existing
        assert note == ""
        registry.execute.assert_not_awaited()


def _test_dictionary() -> AttributeDictionary:
    """测试用受治理词典：style/series 为 option 型，face_price 为 number 型。"""
    definitions = {
        "style": AttributeDefinitionView(
            code="style", name="风格", data_type="option",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
        "series": AttributeDefinitionView(
            code="series", name="系列", data_type="option",
            multi_value=True, searchable=True, hard_filterable=True,
        ),
        "face_price": AttributeDefinitionView(
            code="face_price", name="面价", data_type="number",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
    }
    aliases = [
        AliasEntry(attribute_code="style", option_code="modern",
                   alias="现代风格", normalized="现代风格"),
        AliasEntry(attribute_code="style", option_code="modern",
                   alias="现代", normalized="现代"),
        AliasEntry(attribute_code="style", option_code="nordic",
                   alias="北欧", normalized="北欧"),
        AliasEntry(attribute_code="series", option_code="灵多",
                   alias="灵多", normalized="灵多"),
    ]
    return AttributeDictionary(definitions=definitions, aliases=aliases)


class _FakePlanner:
    """带真实受治理词典的假规划器：语义归一只认词典内的取值。"""

    dictionary = _test_dictionary()


class TestParseJsonObject:
    def test_plain_json(self):
        from app.knowledge.semantic import _parse_json_object

        assert _parse_json_object('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        from app.knowledge.semantic import _parse_json_object

        payload = _parse_json_object('```json\n{"selected": []}\n```')
        assert payload == {"selected": []}

    def test_json_with_surrounding_prose(self):
        from app.knowledge.semantic import _parse_json_object

        payload = _parse_json_object('好的，结果如下：\n{"x": 2}\n以上。')
        assert payload == {"x": 2}

    def test_garbage_returns_empty(self):
        from app.knowledge.semantic import _parse_json_object

        assert _parse_json_object("完全不是 JSON") == {}
        assert _parse_json_object("") == {}
        assert _parse_json_object("[1,2,3]") == {}


class TestScreenProducts:
    def test_selected_products_keep_model_order_and_reasons(self):
        adapter = _adapter(
            '{"selected":[{"product_no":"P-2","reason":"现代风格"},'
            '{"product_no":"P-1","reason":"同为现代"}],"interpretation":"要现代风格的产品"}'
        )
        result = asyncio.run(
            screen_products(
                "现代风格",
                [_candidate("P-1"), _candidate("P-2")],
                adapter=adapter,
                session_id="s",
            )
        )
        assert [p.product_no for p in result.products] == ["P-2", "P-1"]
        assert result.products[0].reason == "现代风格"
        assert result.interpretation == "要现代风格的产品"
        assert result.used is True

    def test_hallucinated_product_no_is_dropped(self):
        adapter = _adapter(
            '{"selected":[{"product_no":"P-404","reason":"编造的"},'
            '{"product_no":"P-1","reason":"真实存在"}]}'
        )
        result = asyncio.run(
            screen_products("现代风格", [_candidate("P-1")], adapter=adapter, session_id="s")
        )
        assert [p.product_no for p in result.products] == ["P-1"]

    def test_duplicate_product_no_is_deduped(self):
        adapter = _adapter(
            '{"selected":[{"product_no":"P-1","reason":"a"},{"product_no":"P-1","reason":"b"}]}'
        )
        result = asyncio.run(
            screen_products("现代风格", [_candidate("P-1")], adapter=adapter, session_id="s")
        )
        assert [p.product_no for p in result.products] == ["P-1"]

    def test_no_fit_returns_empty(self):
        """负向：模型认为没有贴合的产品时必须为空，绝不硬凑。"""
        adapter = _adapter('{"selected":[],"interpretation":"没有巴洛克风格的产品"}')
        result = asyncio.run(
            screen_products(
                "巴洛克式会议桌", [_candidate("P-1")], adapter=adapter, session_id="s"
            )
        )
        assert result.products == ()
        assert result.used is False

    def test_no_candidates_never_calls_model(self):
        adapter = _adapter('{"selected":[{"product_no":"P-1"}]}')
        result = asyncio.run(
            screen_products("现代风格", [], adapter=adapter, session_id="s")
        )
        assert result.products == ()
        adapter.chat.assert_not_awaited()

    def test_none_adapter_never_calls_model(self):
        adapter = _adapter("should not be used")
        result = asyncio.run(
            screen_products(
                "现代风格", [_candidate("P-1")], adapter=NoneAdapter(), session_id="s"
            )
        )
        assert result.products == ()
        adapter.chat.assert_not_awaited()

    def test_adapter_failure_fails_closed(self):
        adapter = MagicMock()
        adapter.chat = AsyncMock(side_effect=TimeoutError("boom"))
        result = asyncio.run(
            screen_products(
                "现代风格", [_candidate("P-1")], adapter=adapter, session_id="s"
            )
        )
        assert result.products == ()

    def test_unparsable_model_output_fails_closed(self):
        adapter = _adapter("我不会选")
        result = asyncio.run(
            screen_products(
                "现代风格", [_candidate("P-1")], adapter=adapter, session_id="s"
            )
        )
        assert result.products == ()

    def test_candidate_card_without_product_no_is_skipped(self):
        adapter = _adapter('{"selected":[]}')
        card = _candidate("P-1")
        card.pop("product_no")
        result = asyncio.run(
            screen_products("现代风格", [card], adapter=adapter, session_id="s")
        )
        assert result.products == ()

    def test_candidate_pool_is_bounded(self):
        adapter = _adapter('{"selected":[]}')
        candidates = [_candidate(f"P-{i}") for i in range(MAX_SCREEN_CANDIDATES + 25)]
        asyncio.run(
            screen_products("现代风格", candidates, adapter=adapter, session_id="s")
        )
        message = adapter.chat.await_args.kwargs["message"]
        assert message.count("product_no") <= MAX_SCREEN_CANDIDATES


class TestAttributeContextLines:
    def _dictionary(self) -> AttributeDictionary:
        definitions = {
            "style": AttributeDefinitionView(
                code="style", name="风格", data_type="option",
                multi_value=False, searchable=True, hard_filterable=True,
            ),
            "face_price": AttributeDefinitionView(
                code="face_price", name="面价", data_type="number",
                multi_value=False, searchable=True, hard_filterable=True,
            ),
        }
        aliases = [
            AliasEntry(
                attribute_code="style", option_code="modern",
                alias="现代风格", normalized="现代风格",
            ),
            AliasEntry(
                attribute_code="style", option_code="modern",
                alias="现代", normalized="现代",
            ),
        ]
        return AttributeDictionary(
            definitions=definitions, aliases=aliases,
        )

    def test_lines_carry_labels_and_chinese_aliases(self):
        lines = attribute_context_lines(self._dictionary())
        assert len(lines) == 1
        # 「现代风格」必须出现在给模型的词典上下文里，否则模型无从归一
        assert "现代风格" in lines[0]
        assert "style(风格)" in lines[0]
        assert "modern=现代风格|现代" in lines[0]

    def test_non_option_definitions_are_skipped(self):
        lines = attribute_context_lines(self._dictionary())
        assert all("face_price" not in line for line in lines)


class TestPlanningInstructions:
    def test_dictionary_context_has_chinese_aliases(self):
        definitions = {
            "style": AttributeDefinitionView(
                code="style", name="风格", data_type="option",
                multi_value=False, searchable=True, hard_filterable=True,
            ),
        }
        aliases = [
            AliasEntry(
                attribute_code="style", option_code="modern",
                alias="现代风格", normalized="现代风格",
            ),
        ]
        dictionary = AttributeDictionary(definitions=definitions, aliases=aliases)
        text = _planning_instructions([], {"product.search"}, dictionary)
        assert "现代风格" in text
        assert "modern(现代风格)" in text

    def test_instructions_tell_model_to_normalize_natural_phrasing(self):
        text = _planning_instructions([], {"product.search"}, None)
        assert "偏现代风格" in text
        assert "style=modern" in text


class TestGatewayScreening:
    def _gateway(self, adapter) -> KnowledgeGateway:
        gateway = KnowledgeGateway.__new__(KnowledgeGateway)
        gateway.adapter = adapter
        return gateway

    def _plan(self) -> QueryPlan:
        return QueryPlan(intent="product_search", required_tools=["product.search"])

    def _request(self) -> KnowledgeQueryRequest:
        return KnowledgeQueryRequest(message="现代风格")

    def test_existing_products_are_untouched(self):
        gateway = self._gateway(_adapter("{}"))
        products = [_candidate("P-1", match_tier="exact")]
        out, note = asyncio.run(
            gateway._screen_candidates(
                self._request(), self._plan(), products,
                [_candidate("P-2")], session_id="s",
            )
        )
        assert out == products
        assert note == ""

    def test_screened_cards_are_marked_and_ordered(self):
        adapter = _adapter(
            '{"selected":[{"product_no":"P-2","reason":"最贴近现代风格"}],'
            '"interpretation":"用户要现代风格"}'
        )
        gateway = self._gateway(adapter)
        out, note = asyncio.run(
            gateway._screen_candidates(
                self._request(), self._plan(), [],
                [_candidate("P-1"), _candidate("P-2")], session_id="s",
            )
        )
        assert [c["product_no"] for c in out] == ["P-2"]
        assert out[0]["match_tier"] == "semantic"
        assert out[0]["match_reason"] == "最贴近现代风格"
        assert note == "用户要现代风格"

    def test_no_candidates_means_no_screening_call(self):
        adapter = _adapter('{"selected":[{"product_no":"P-1"}]}')
        gateway = self._gateway(adapter)
        out, note = asyncio.run(
            gateway._screen_candidates(
                self._request(), self._plan(), [], [], session_id="s"
            )
        )
        assert out == []
        assert note == ""
        adapter.chat.assert_not_awaited()

    def test_non_product_plan_is_not_screened(self):
        adapter = _adapter('{"selected":[{"product_no":"P-1"}]}')
        gateway = self._gateway(adapter)
        plan = QueryPlan(intent="knowledge_question", required_tools=[])
        out, note = asyncio.run(
            gateway._screen_candidates(
                self._request(), plan, [], [_candidate("P-1")], session_id="s"
            )
        )
        assert out == []
        adapter.chat.assert_not_awaited()

    def test_negative_stays_empty(self):
        adapter = _adapter('{"selected":[],"interpretation":"没有巴洛克风格"}')
        gateway = self._gateway(adapter)
        out, note = asyncio.run(
            gateway._screen_candidates(
                KnowledgeQueryRequest(message="巴洛克式会议桌"),
                self._plan(), [], [_candidate("P-1")], session_id="s",
            )
        )
        assert out == []
        assert note == "没有巴洛克风格"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
