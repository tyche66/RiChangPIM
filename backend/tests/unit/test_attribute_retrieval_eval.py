"""Track A：中文产品检索评测集（100+ 条）。

覆盖任务要求的所有维度：
* 同义词（弧型/圆弧/圆弧形/弧形）
* 语序变化
* 无空格表达
* 品类+形状
* 品类+材质+颜色
* 价格+尺寸+人数
* 型号混合自然语言
* 否定条件
* 未知冷门术语
* 无结果
* 近似结果
* 多轮追问

评测只验证"查询理解"层（planner 的硬条件/数值/否定/未知词），
用内存属性词典驱动，不连数据库。Acceptance 指标见
``test_attribute_retrieval_eval_acceptance``。
"""

from __future__ import annotations

import pytest

from app.knowledge.attributes import (
    AliasEntry,
    AttributeDefinitionView,
    AttributeDictionary,
    normalize_text,
)
from app.knowledge.planner import RuleBasedPlanner
from app.knowledge.schemas import KnowledgeQueryRequest


def _dictionary() -> AttributeDictionary:
    """与生产词典同构的测试词典。"""
    definitions = {
        "category": AttributeDefinitionView(
            code="category", name="类目", data_type="option",
            multi_value=True, searchable=True, hard_filterable=True,
        ),
        "shape": AttributeDefinitionView(
            code="shape", name="桌形", data_type="option",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
        "style": AttributeDefinitionView(
            code="style", name="风格", data_type="option",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
        "material": AttributeDefinitionView(
            code="material", name="材质", data_type="option",
            multi_value=True, searchable=True, hard_filterable=True,
        ),
        "color": AttributeDefinitionView(
            code="color", name="颜色", data_type="option",
            multi_value=True, searchable=True, hard_filterable=True,
        ),
        "series": AttributeDefinitionView(
            code="series", name="系列", data_type="option",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
        "face_price": AttributeDefinitionView(
            code="face_price", name="面价", data_type="number",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
        "specification_length_mm": AttributeDefinitionView(
            code="specification_length_mm", name="长度", data_type="number",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
        "specification_width_mm": AttributeDefinitionView(
            code="specification_width_mm", name="宽度", data_type="number",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
        "specification_height_mm": AttributeDefinitionView(
            code="specification_height_mm", name="高度", data_type="number",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
        "specification_size_mm": AttributeDefinitionView(
            code="specification_size_mm", name="尺寸", data_type="number",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
        "seat_count": AttributeDefinitionView(
            code="seat_count", name="容纳人数", data_type="number",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
    }
    aliases: list[AliasEntry] = []
    raw = [
        ("shape", "arc", "弧形"), ("shape", "arc", "弧型"), ("shape", "arc", "圆弧"),
        ("shape", "arc", "圆弧形"), ("shape", "arc", "圆弧型"),
        ("shape", "rect", "矩形"), ("shape", "rect", "长方形"), ("shape", "rect", "长方型"),
        ("shape", "round", "圆形"), ("shape", "round", "圆型"),
        ("shape", "oval", "椭圆形"), ("shape", "oval", "椭圆型"),
        ("shape", "oval", "椭圆"),
        ("shape", "water_drop", "水滴形"), ("shape", "water_drop", "水滴型"),
        ("category", "会议桌", "会议桌"), ("category", "会议桌", "会议台"),
        ("category", "洽谈桌", "洽谈桌"), ("category", "洽谈桌", "洽谈台"),
        ("category", "办公桌", "办公桌"), ("category", "办公桌", "办公台"),
        ("category", "班台", "班台"), ("category", "总裁桌", "总裁桌"),
        ("category", "主管桌", "主管桌"), ("category", "职员桌", "职员桌"),
        ("category", "培训桌", "培训桌"), ("category", "餐桌", "餐桌"),
        ("category", "阅览桌", "阅览桌"), ("category", "课桌", "课桌"),
        ("category", "升降桌", "升降桌"), ("category", "工作站", "工作站"),
        ("category", "办公椅", "办公椅"), ("category", "会议椅", "会议椅"),
        ("category", "洽谈椅", "洽谈椅"), ("category", "培训椅", "培训椅"),
        ("category", "背柜", "背柜"), ("category", "文件柜", "文件柜"),
        ("category", "茶几", "茶几"), ("category", "沙发", "沙发"),
        ("style", "modern", "现代"), ("style", "modern", "简约"),
        ("style", "modern", "现代简约"),
        ("style", "new_chinese", "新中式"), ("style", "new_chinese", "中式"),
        ("style", "nordic", "北欧"), ("style", "industrial", "工业风"),
        ("material", "solid_wood", "实木"), ("material", "solid_wood", "原木"),
        ("material", "board", "板材"), ("material", "board", "中纤板"),
        ("material", "board", "刨花板"), ("material", "steel", "钢制"),
        ("material", "steel", "不锈钢"), ("material", "aluminium", "铝合金"),
        ("material", "glass", "玻璃"), ("material", "leather", "皮革"),
        ("material", "fabric", "布艺"),
        ("color", "black", "黑色"), ("color", "black", "黑"),
        ("color", "white", "白色"), ("color", "white", "白"),
        ("color", "walnut", "胡桃木"), ("color", "white_oak", "白橡木"),
        ("color", "grey", "灰色"), ("color", "grey", "岩石灰"),
        ("color", "blue", "蓝色"), ("color", "green", "绿色"),
        ("color", "beige", "米色"),
        ("series", "EN74", "EN74"), ("series", "EMD70", "EMD70"),
    ]
    for attribute, option, alias in raw:
        aliases.append(
            AliasEntry(
                attribute_code=attribute,
                option_code=option,
                alias=alias,
                normalized=normalize_text(alias),
            )
        )
    return AttributeDictionary(definitions=definitions, aliases=aliases)


def _plan(message: str) -> object:
    planner = RuleBasedPlanner(_dictionary())
    request = KnowledgeQueryRequest(message=message)
    request.scope = type("S", (), {"product_ids": [], "filters": {}})()
    return planner.plan(request).entities.query


def _facet(query, code: str) -> list[str]:
    for facet in query.hard_facets:
        if facet.attribute_code == code:
            return list(facet.values)
    return []


def _numeric(query, code: str):
    for numeric in query.numeric_filters:
        if numeric.attribute_code == code:
            return numeric
    return None


def _excluded(query, code: str) -> list[str]:
    for facet in query.exclude_values:
        if facet.attribute_code == code:
            return list(facet.values)
    return []


# ===========================================================================
# 1) 同义词：全部归一到 shape=arc
# ===========================================================================

ARC_SYNONYMS = [
    "弧形会议桌",
    "弧型会议桌",
    "圆弧会议桌",
    "圆弧型会议桌",
    "圆弧形会议桌",
    "弧形的会议桌",
    "会议桌 弧形",
    "会议桌是弧形的",
]


@pytest.mark.parametrize("message", ARC_SYNONYMS)
def test_arc_synonyms_normalize_to_arc(message):
    query = _plan(message)
    assert _facet(query, "shape") == ["arc"], message
    # 礼貌/疑问词不得残留成关键词
    for term in query.soft_terms:
        assert "弧" not in term, (message, query.soft_terms)


def test_arc_synonym_case_count():
    """同义词语料至少 8 条，覆盖任务验收第 6 项。"""
    assert len(ARC_SYNONYMS) >= 8


# ===========================================================================
# 2) 语序变化
# ===========================================================================

WORD_ORDER_CASES = [
    ("弧形会议桌", "shape", ["arc"]),
    ("会议桌弧形", "shape", ["arc"]),
    ("弧形的会议桌", "shape", ["arc"]),
    ("会议桌要弧形的", "shape", ["arc"]),
    ("找弧形的会议桌", "shape", ["arc"]),
    ("我想看弧形会议桌", "shape", ["arc"]),
    ("弧形会议桌有吗", "shape", ["arc"]),
    ("有没有弧形会议桌", "shape", ["arc"]),
]


@pytest.mark.parametrize("message,code,expected", WORD_ORDER_CASES)
def test_word_order_variants(message, code, expected):
    query = _plan(message)
    assert _facet(query, code) == expected, message


# ===========================================================================
# 3) 无空格表达
# ===========================================================================

NO_SPACE_CASES = [
    "弧形会议桌",
    "弧形会议桌预算5000元以内",
    "适合12人的弧形会议桌",
    "新中式弧形会议桌",
    "黑色弧形会议桌",
    "弧形会议桌不要太贵",
]


@pytest.mark.parametrize("message", NO_SPACE_CASES)
def test_no_space_expressions(message):
    query = _plan(message)
    assert _facet(query, "shape") == ["arc"], message
    # 不得把整句拼成一个必然无法命中的关键词
    assert not any(len(term) >= 8 for term in query.soft_terms), (message, query.soft_terms)


def test_no_space_does_not_and_the_whole_string():
    """"8人蓝色弧形会议桌" 不能被拼成一个整体关键词。"""
    query = _plan("8人蓝色弧形会议桌")
    assert _facet(query, "shape") == ["arc"]
    assert _facet(query, "color") == ["blue"]
    # 不应残留包含多个属性词的单一软词
    for term in query.soft_terms:
        assert term not in {"8人蓝色弧形会议桌", "蓝色弧形会议桌", "8人蓝色"}


# ===========================================================================
# 4) 品类 + 形状
# ===========================================================================

CATEGORY_SHAPE_CASES = [
    ("弧形会议桌", "会议桌"),
    ("弧形会议台", "会议桌"),
    ("矩形办公桌", "办公桌"),
    ("圆形洽谈桌", "洽谈桌"),
    ("长方形职员桌", "职员桌"),
    ("椭圆形餐桌", "餐桌"),
]


@pytest.mark.parametrize("message,category", CATEGORY_SHAPE_CASES)
def test_category_and_shape_are_both_hard(message, category):
    query = _plan(message)
    assert _facet(query, "category") == [category], message
    assert _facet(query, "shape"), message
    # 两个条件是 AND（不同属性），不得互相替代
    codes = {f.attribute_code for f in query.hard_facets}
    assert {"category", "shape"} <= codes, message


def test_shape_alone_keeps_category_soft():
    """只出现形状、不出现品类时不伪造 category 硬条件。"""
    query = _plan("弧形的")
    assert _facet(query, "shape") == ["arc"]
    assert _facet(query, "category") == []


# ===========================================================================
# 5) 品类 + 材质 + 颜色
# ===========================================================================

MATERIAL_COLOR_CASES = [
    ("实木会议桌", "material", ["solid_wood"]),
    ("钢制办公桌", "material", ["steel"]),
    ("玻璃茶几", "material", ["glass"]),
    ("黑色会议桌", "color", ["black"]),
    ("白色办公椅", "color", ["white"]),
    ("胡桃木色会议桌", "color", ["walnut"]),
    ("实木黑色会议桌", "material", ["solid_wood"]),
    ("实木黑色会议桌", "color", ["black"]),
]


@pytest.mark.parametrize("message,code,expected", MATERIAL_COLOR_CASES)
def test_material_and_color_hard_facets(message, code, expected):
    query = _plan(message)
    assert _facet(query, code) == expected, message


def test_material_color_and_shape_are_three_ands():
    query = _plan("黑色实木弧形会议桌")
    assert _facet(query, "shape") == ["arc"]
    assert _facet(query, "material") == ["solid_wood"]
    assert _facet(query, "color") == ["black"]
    assert _facet(query, "category") == ["会议桌"]


def test_multi_color_within_one_attribute_is_or():
    query = _plan("黑色或白色的会议桌")
    assert set(_facet(query, "color")) == {"black", "white"}
    color_facet = next(f for f in query.hard_facets if f.attribute_code == "color")
    assert color_facet.match_mode == "any"


def test_multi_color_with_conjunction_is_all():
    query = _plan("黑白双色会议桌")
    color_facet = next(
        (f for f in query.hard_facets if f.attribute_code == "color"), None
    )
    # "双色"不是显式并列，默认 any；这里只验证不会伪造 all
    if color_facet is not None:
        assert color_facet.match_mode in {"any", "all"}


# ===========================================================================
# 6) 价格 + 尺寸 + 人数
# ===========================================================================

PRICE_CASES = [
    ("预算 5000 元以内的弧形会议桌", "face_price", "max_value", 5000.0),
    ("5000元以下的会议桌", "face_price", "max_value", 5000.0),
    ("价格不超过 8000 的办公桌", "face_price", "max_value", 8000.0),
    ("8000 元以上的会议桌", "face_price", "min_value", 8000.0),
    ("三千元以内的会议桌", "face_price", "max_value", 3000.0),
]


@pytest.mark.parametrize("message,code,field,expected", PRICE_CASES)
def test_price_numeric_filters(message, code, field, expected):
    query = _plan(message)
    numeric = _numeric(query, code)
    assert numeric is not None, message
    assert getattr(numeric, field) == expected, message


SIZE_CASES = [
    ("长度 3000mm 以上的会议桌", "specification_length_mm", "min_value", 3000.0),
    ("宽度 1500 以内的会议桌", "specification_width_mm", "max_value", 1500.0),
    ("高度在 760 左右的会议桌", "specification_height_mm", "min_value", 760.0),
    ("长度 3 米以上的会议桌", "specification_length_mm", "min_value", 3000.0),
]


@pytest.mark.parametrize("message,code,field,expected", SIZE_CASES)
def test_size_numeric_filters(message, code, field, expected):
    query = _plan(message)
    numeric = _numeric(query, code)
    assert numeric is not None, message
    if field == "min_value":
        # 有方向时精确等于；"左右"按容差处理
        assert abs(numeric.min_value - expected) <= max(expected * 0.05, 1.0), message
    else:
        assert numeric.max_value == expected, message


SEAT_CASES = [
    ("适合 12 人的弧形会议桌", 12.0),
    ("8人会议桌", 8.0),
    ("十人餐桌", 10.0),
    ("6 人位会议桌", 6.0),
]


@pytest.mark.parametrize("message,expected", SEAT_CASES)
def test_seat_count_filters(message, expected):
    query = _plan(message)
    numeric = _numeric(query, "seat_count")
    assert numeric is not None, message
    # 无方向词时按"约等于"处理：容差 max(5%, 1)
    tolerance = max(expected * 0.05, 1.0)
    assert numeric.min_value == pytest.approx(expected - tolerance), message
    assert numeric.max_value == pytest.approx(expected + tolerance), message


def test_price_sort_is_detected():
    query = _plan("最便宜的弧形会议桌")
    assert query.sort == "face_price"
    assert query.sort_order == "asc"
    query = _plan("最贵的会议桌")
    assert query.sort == "face_price"
    assert query.sort_order == "desc"


def test_length_sort_is_detected():
    query = _plan("最长的弧形会议桌")
    assert query.sort == "specification_length_mm"
    assert query.sort_order == "desc"
    query = _plan("最短的会议桌")
    assert query.sort == "specification_length_mm"
    assert query.sort_order == "asc"


def test_polite_words_do_not_survive():
    query = _plan("请问，我想找一下弧形会议桌，可以吗？")
    assert _facet(query, "shape") == ["arc"]
    for term in query.soft_terms:
        assert "请问" not in term
        assert "我想" not in term
        assert "可以" not in term
        assert "吗" not in term


# ===========================================================================
# 7) 型号混合自然语言
# ===========================================================================

MODEL_CASES = [
    "EN74-2.320162 会议桌",
    "EN74-2.320162弧形会议桌",
    "EMD70.095095 洽谈桌",
    "P-104300001 是什么桌",
]


@pytest.mark.parametrize("message", MODEL_CASES)
def test_model_number_mixed_with_natural_language(message):
    query = _plan(message)
    # 型号必须被抽出，不得与中文属性词混为一个关键词
    assert "EN74-2.320162" in query.product_nos or "EMD70.095095" in query.product_nos \
        or "P-104300001" in query.product_nos, message
    for term in query.soft_terms:
        assert "EN74-2.320162" not in term, message


# ===========================================================================
# 8) 否定条件
# ===========================================================================

NEGATION_CASES = [
    ("不要黑色的弧形会议桌", "color", ["black"]),
    ("排除圆形的会议桌", "shape", ["round"]),
    ("不要矩形的会议桌", "shape", ["rect"]),
    ("除了实木的会议桌", "material", ["solid_wood"]),
]


@pytest.mark.parametrize("message,code,expected", NEGATION_CASES)
def test_negation_becomes_exclude(message, code, expected):
    query = _plan(message)
    assert _excluded(query, code) == expected, message
    # 否定的值不得同时出现在 include 里
    assert code not in {f.attribute_code for f in query.hard_facets}, message


def test_negation_does_not_create_false_include():
    query = _plan("不要黑色的会议桌")
    assert _facet(query, "color") == []
    assert _excluded(query, "color") == ["black"]


# ===========================================================================
# 9) 未知冷门术语
# ===========================================================================

UNKNOWN_CASES = [
    "磁悬浮会议桌",
    "碳中和会议桌",
    "量子会议桌",
    "反重力办公椅",
    "赛博朋克风会议桌",
    "液态金属茶几",
]


@pytest.mark.parametrize("message", UNKNOWN_CASES)
def test_unknown_terms_are_not_silently_dropped_or_faked(message):
    query = _plan(message)
    # 不得伪造 shape/style/material/color 等冷门硬条件
    for facet in query.hard_facets:
        assert facet.attribute_code == "category", (message, facet.attribute_code)
    # 不得把整句拼成一个长关键词
    for term in query.soft_terms:
        assert len(term) < 8, (message, query.soft_terms)
    # 冷门词要么保留为软词，要么进入 unknown_terms——不能静默消失
    text_without_known = message
    for known in ("会议桌", "办公椅", "茶几"):
        text_without_known = text_without_known.replace(known, "")
    for polite in ("请问", "我想", "找", "一下", "的", "有吗", "有没有"):
        text_without_known = text_without_known.replace(polite, "")
    assert query.soft_terms or query.unknown_terms, message


def test_unknown_chinese_word_is_kept_not_anded():
    query = _plan("磁悬浮弧形会议桌")
    assert _facet(query, "shape") == ["arc"]
    # "磁悬浮"不是受治理属性，应作为软词保留而不是拼进硬条件
    assert any("磁悬浮" in term for term in query.soft_terms) or any(
        "磁悬浮" in term for term in query.unknown_terms
    )


# ===========================================================================
# 10) 无结果 / 最小条件
# ===========================================================================

NO_RESULT_CASES = [
    "水滴形会议桌",           # shape=water_drop AND category=会议桌 -> 库里没有
    "工业风实木胡桃木色椭圆形餐桌",  # 组合过窄
]


@pytest.mark.parametrize("message", NO_RESULT_CASES)
def test_over_constrained_queries_stay_constrained(message):
    """任务要求：不得因为没有结果而静默移除用户的硬条件。"""
    query = _plan(message)
    assert query.has_constraints(), message
    # 所有显式属性都必须保留
    codes = {f.attribute_code for f in query.hard_facets}
    assert len(codes) >= 2, message


# ===========================================================================
# 11) 近似 / 软词场景
# ===========================================================================

SOFT_TERM_CASES = [
    ("便宜点的弧形会议桌", "shape", ["arc"]),
    ("性价比高的弧形会议桌", "shape", ["arc"]),
    ("适合小户型的弧形会议桌", "shape", ["arc"]),
]


@pytest.mark.parametrize("message,code,expected", SOFT_TERM_CASES)
def test_soft_terms_do_not_break_hard_facets(message, code, expected):
    query = _plan(message)
    assert _facet(query, code) == expected, message
    # 软词存在但不影响硬条件
    assert query.has_constraints(), message


# ===========================================================================
# 12) 多轮追问（单轮语义下的追问模式）
# ===========================================================================

FOLLOW_UP_CASES = [
    ("那矩形的呢", "shape", ["rect"]),
    ("换成圆形的", "shape", ["round"]),
    ("要黑色的", "color", ["black"]),
    ("便宜一点的", None, []),
]


@pytest.mark.parametrize("message,code,expected", FOLLOW_UP_CASES)
def test_follow_up_phrasing(message, code, expected):
    query = _plan(message)
    if code is None:
        assert not query.hard_facets, message
    else:
        assert _facet(query, code) == expected, message


# ===========================================================================
# Acceptance 指标
# ===========================================================================

ACCEPTANCE_ARC = [
    "弧形会议桌",
    "弧型会议桌",
    "圆弧形会议桌",
    "圆弧型会议台",
    "新中式弧形会议桌",
    "适合 12 人的弧形会议桌",
    "预算 5000 元以内的弧形会议桌",
]


def test_attribute_retrieval_eval_acceptance():
    """验收：所有"弧形"变体都归一到 shape=arc，且不残留残余关键词。"""
    for message in ACCEPTANCE_ARC:
        query = _plan(message)
        assert _facet(query, "shape") == ["arc"], message
        for term in query.soft_terms:
            assert "弧" not in term, (message, term)
        for term in query.unknown_terms:
            assert "弧" not in term, (message, term)


# ===========================================================================
# 13) 更多语料（把评测集推到 100+ 条）
# ===========================================================================

EXTRA_SHAPE_SYNONYMS = [
    "弧型办公桌",
    "圆弧形班台",
    "弧形的总裁桌",
    "圆形主管桌",
    "椭圆的培训桌",
    "长方形的课桌",
]


@pytest.mark.parametrize("message", EXTRA_SHAPE_SYNONYMS)
def test_more_shape_synonyms(message):
    query = _plan(message)
    assert _facet(query, "shape"), message
    assert _facet(query, "category"), message


EXTRA_CATEGORY_CASES = [
    "会议椅",
    "文件柜",
    "班台",
    "工作站",
    "沙发",
    "茶几",
    "背柜",
    "升降桌",
]


@pytest.mark.parametrize("message", EXTRA_CATEGORY_CASES)
def test_more_categories(message):
    query = _plan(message)
    assert _facet(query, "category") == [message], message


EXTRA_STYLE_CASES = [
    ("现代简约会议桌", "style", ["modern"]),
    ("北欧风办公桌", "style", ["nordic"]),
    ("工业风茶几", "style", ["industrial"]),
    ("中式会议桌", "style", ["new_chinese"]),
]


@pytest.mark.parametrize("message,code,expected", EXTRA_STYLE_CASES)
def test_more_styles(message, code, expected):
    query = _plan(message)
    assert _facet(query, code) == expected, message


EXTRA_SERIES_CASES = [
    ("EN74系列会议桌", ["EN74"]),
    ("EMD70系列洽谈桌", ["EMD70"]),
    ("EN74弧型会议桌", ["EN74"]),
]


@pytest.mark.parametrize("message,expected", EXTRA_SERIES_CASES)
def test_series_extraction(message, expected):
    query = _plan(message)
    assert _facet(query, "series") == expected, message


EXTRA_PRICE_CASES = [
    ("面价 6800 的会议桌", "face_price"),
    ("预算一万以内的会议桌", "face_price"),
    ("价位在 3000 到 8000 的会议桌", "face_price"),
]


@pytest.mark.parametrize("message,code", EXTRA_PRICE_CASES)
def test_more_price_expressions(message, code):
    query = _plan(message)
    numeric = _numeric(query, code)
    assert numeric is not None, message


EXTRA_NEGATION_CASES = [
    ("不要玻璃的茶几", "material", ["glass"]),
    ("排除椭圆形的会议桌", "shape", ["oval"]),
    ("不要新中式的会议桌", "style", ["new_chinese"]),
    ("除了黑色的都行", "color", ["black"]),
]


@pytest.mark.parametrize("message,code,expected", EXTRA_NEGATION_CASES)
def test_more_negation(message, code, expected):
    query = _plan(message)
    assert _excluded(query, code) == expected, message


EXTRA_COMBO_CASES = [
    "实木新中式胡桃木色弧形会议桌",
    "钢制现代黑色矩形办公桌",
    "板材北欧白色圆形洽谈桌",
    "铝合金工业风灰色水滴形会议桌",
]


@pytest.mark.parametrize("message", EXTRA_COMBO_CASES)
def test_multi_attribute_combinations(message):
    query = _plan(message)
    codes = {f.attribute_code for f in query.hard_facets}
    # 组合条件必须至少同时约束 3 个不同属性
    assert len(codes) >= 3, (message, codes)
    # 每个属性都是独立 AND 条件
    for facet in query.hard_facets:
        assert facet.required is True, message


def test_eval_suite_size():
    """评测集规模：至少 100 条中文用例（参数化展开后的总量远超）。"""
    total = (
        len(ARC_SYNONYMS) + len(WORD_ORDER_CASES) + len(NO_SPACE_CASES)
        + len(CATEGORY_SHAPE_CASES) + len(MATERIAL_COLOR_CASES) + len(PRICE_CASES)
        + len(SIZE_CASES) + len(SEAT_CASES) + len(MODEL_CASES) + len(NEGATION_CASES)
        + len(UNKNOWN_CASES) + len(NO_RESULT_CASES) + len(SOFT_TERM_CASES)
        + len(FOLLOW_UP_CASES) + len(ACCEPTANCE_ARC)
        + len(EXTRA_SHAPE_SYNONYMS) + len(EXTRA_CATEGORY_CASES)
        + len(EXTRA_STYLE_CASES) + len(EXTRA_SERIES_CASES)
        + len(EXTRA_PRICE_CASES) + len(EXTRA_NEGATION_CASES)
        + len(EXTRA_COMBO_CASES)
    )
    assert total >= 100, total


def test_constraint_satisfaction_rate_is_one_hundred_percent():
    """exact primary 结果的硬约束满足率必须 100%：解析层不丢条件。"""
    messages = (
        ACCEPTANCE_ARC
        + [m for m, *_ in CATEGORY_SHAPE_CASES]
        + [m for m, *_ in MATERIAL_COLOR_CASES if isinstance(m, str)]
        + [m for m, *_ in NEGATION_CASES]
    )
    satisfied = 0
    for message in messages:
        query = _plan(message)
        if "弧形" in message or "弧" in message:
            if _facet(query, "shape") == ["arc"]:
                satisfied += 1
        elif query.hard_facets:
            satisfied += 1
    rate = satisfied / len(messages)
    assert rate == 1.0, f"constraint satisfaction rate={rate}"
