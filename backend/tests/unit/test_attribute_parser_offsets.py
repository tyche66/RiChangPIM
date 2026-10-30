"""Track A：属性解析器的坐标换算与长尾查询验收。

修复的缺陷
----------
``normalize_text()`` 会去掉空格与标点，而 ``extract_alias_hits()`` 返回的是
**归一化串**上的命中位置；``_residual_text()`` 却用这些位置去切**原文**。
带空格、标点或中英混排的查询里，残余词会被错误截断（例如
``"弧形 会议桌，不要黑色"`` 会把 ``，不`` 当成命中区间抹掉，残留出
``要黑色`` 这种垃圾词）。

现在 ``extract_alias_hits`` 通过 ``normalize_text_with_map()`` 把命中位置
换算回原文坐标，本文档的用例锁住这一点。

覆盖的长尾查询要求
------------------
* 否定条件（含空格/标点变体）；
* 同义词与语序变化；
* 产品编号混合自然语言；
* 材质/颜色/尺寸/人数/价格组合；
* 未知属性不被静默丢弃；
* 精确/部分/文本/语义结果分层（``match_tier``）。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.knowledge.attributes import (
    AliasEntry,
    AttributeDefinitionView,
    AttributeDictionary,
    build_product_query,
    extract_alias_hits,
    normalize_text,
    normalize_text_with_map,
)
from app.knowledge.planner import RuleBasedPlanner
from app.knowledge.schemas import KnowledgeQueryRequest
from app.knowledge.tools.product import ProductSearchInput, _build_product_search_statement

# ---------------------------------------------------------------------------
# 词典（与生产词典同构，纯内存）
# ---------------------------------------------------------------------------


def _view(code: str, data_type: str = "option") -> AttributeDefinitionView:
    return AttributeDefinitionView(
        code=code,
        name=code,
        data_type=data_type,
        multi_value=data_type == "option",
        searchable=True,
        hard_filterable=True,
    )


def _entry(attribute_code: str, option_code: str, alias: str) -> AliasEntry:
    return AliasEntry(
        attribute_code=attribute_code,
        option_code=option_code,
        alias=alias,
        normalized=normalize_text(alias),
    )


DICTIONARY = AttributeDictionary(
    definitions={
        "category": _view("category"),
        "shape": _view("shape"),
        "material": _view("material"),
        "color": _view("color"),
        "style": _view("style"),
        "series": _view("series"),
        "specification_length_mm": _view("specification_length_mm", "number"),
        "specification_width_mm": _view("specification_width_mm", "number"),
        "specification_height_mm": _view("specification_height_mm", "number"),
        "seat_count": _view("seat_count", "number"),
        "face_price": _view("face_price", "number"),
    },
    aliases=[
        _entry("shape", "arc", "弧形"),
        _entry("shape", "arc", "弧型"),
        _entry("shape", "arc", "圆弧形"),
        _entry("shape", "arc", "圆弧型"),
        _entry("shape", "rect", "矩形"),
        _entry("shape", "round", "圆形"),
        _entry("shape", "oval", "椭圆形"),
        _entry("category", "会议桌", "会议桌"),
        _entry("category", "洽谈桌", "洽谈桌"),
        _entry("material", "glass", "玻璃"),
        _entry("material", "steel", "钢制"),
        _entry("material", "solid_wood", "实木"),
        _entry("color", "black", "黑色"),
        _entry("color", "white", "白色"),
        _entry("style", "modern", "现代"),
        _entry("style", "new_chinese", "新中式"),
        _entry("series", "EN74", "EN74系列"),
    ],
)


def _facet(query, code: str) -> list[str] | None:
    for facet in query.hard_facets:
        if facet.attribute_code == code:
            return facet.values
    return None


def _excluded(query, code: str) -> list[str] | None:
    for facet in query.exclude_values:
        if facet.attribute_code == code:
            return facet.values
    return None


def _numeric(query, code: str):
    for filter_ in query.numeric_filters:
        if filter_.attribute_code == code:
            return filter_
    return None


def _plan(message: str):
    return build_product_query(message, DICTIONARY)


# ---------------------------------------------------------------------------
# 1) 归一化坐标映射
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message, expected",
    [
        ("弧形会议桌", "弧形会议桌"),
        ("弧形 会议桌", "弧形会议桌"),
        ("弧形、会议桌", "弧形会议桌"),
        ("弧形-会议桌", "弧形会议桌"),
        ("PU 弧形会议桌", "pu弧形会议桌"),
    ],
)
def test_normalize_text_with_map_matches_normalize_text(message, expected):
    normalized, index_map = normalize_text_with_map(message)
    assert normalized == normalize_text(message)
    assert normalized == expected
    assert len(index_map) == len(normalized)


def test_normalize_text_with_map_points_back_to_original_chars():
    message = "弧形 会议桌，不要黑色"
    normalized, index_map = normalize_text_with_map(message)
    assert normalized == "弧形会议桌不要黑色"
    # "不要" 在原文里是下标 7、8（"弧形 会议桌，" 占 0-6）
    assert message[index_map[5] : index_map[5] + 2] == "不要"
    # 每个归一化下标都能还原出原文里"同一个"字符
    for _norm_index, original_index in enumerate(index_map):
        assert message[original_index] not in (" ", "，")


# ---------------------------------------------------------------------------
# 2) 命中位置落在原文坐标上（回归用例）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message, alias, expected_slice",
    [
        ("弧形 会议桌，不要黑色", "弧形", "弧形"),
        ("弧形 会议桌，不要黑色", "黑色", "黑色"),
        ("弧形会议桌(不要玻璃)", "弧形", "弧形"),
        ("弧形会议桌(不要玻璃)", "玻璃", "玻璃"),
        ("玻璃 钢制 弧形 会议桌", "弧形", "弧形"),
        ("PU 弧形 会议桌，排除 白色", "弧形", "弧形"),
        ("会议桌：弧形 + 玻璃 + 白色", "玻璃", "玻璃"),
        ("弧形会议桌;不要 黑色", "黑色", "黑色"),
    ],
)
def test_alias_hits_are_in_original_coordinates(message, alias, expected_slice):
    hits = extract_alias_hits(message, DICTIONARY)
    matched = [h for h in hits if h.entry.alias == alias]
    assert matched, message
    for hit in matched:
        assert message[hit.start : hit.end] == expected_slice


def test_residual_text_does_not_leak_negation_fragments():
    """带空格+标点时，残余词不应再出现"要黑色/不玻璃"这类垃圾碎片。"""
    query = _plan("弧形 会议桌，不要黑色")
    assert _facet(query, "shape") == ["arc"]
    assert _excluded(query, "color") == ["black"]
    for term in query.soft_terms + query.unknown_terms:
        assert "黑色" not in term
        assert "不要" not in term
        assert "弧形" not in term
    # "会议桌"是品类别名，会被消耗掉，残余里不该再出现它
    assert all("会议桌" not in term for term in query.soft_terms + query.unknown_terms)


def test_punctuation_between_attributes_does_not_break_matching():
    query = _plan("弧形会议桌（玻璃 + 黑色）")
    assert _facet(query, "shape") == ["arc"]
    assert _facet(query, "material") == ["glass"]
    assert _facet(query, "color") == ["black"]


def test_mixed_latin_and_chinese_query_keeps_offsets():
    query = _plan("PU弧形会议桌,不要黑色")
    assert _facet(query, "shape") == ["arc"]
    assert _excluded(query, "color") == ["black"]


# ---------------------------------------------------------------------------
# 3) 长尾查询验收（解析层）
# ---------------------------------------------------------------------------


NEGATION_LONG_TAIL = [
    ("弧形会议桌 不要 黑色", "color", ["black"]),
    ("弧形会议桌,排除圆形", "shape", ["round"]),
    ("弧形会议桌：不要玻璃的", "material", ["glass"]),
    ("弧形会议桌（非黑色）", "color", ["black"]),
    ("弧形会议桌 — 不要黑色", "color", ["black"]),
]


@pytest.mark.parametrize("message, code, expected", NEGATION_LONG_TAIL)
def test_negation_variants_with_spacing(message, code, expected):
    query = _plan(message)
    assert _facet(query, "shape") == ["arc"]
    assert _excluded(query, code) == expected


WORD_ORDER_LONG_TAIL = [
    ("弧形 的 会议桌", "shape", ["arc"]),
    ("玻璃弧形会议桌", "material", ["glass"]),
    ("黑色弧形会议桌", "color", ["black"]),
    ("弧形玻璃会议桌", "material", ["glass"]),
    ("会议桌玻璃弧形", "shape", ["arc"]),
]


@pytest.mark.parametrize("message, expected_code, expected_values", WORD_ORDER_LONG_TAIL)
def test_word_order_and_spacing(message, expected_code, expected_values):
    query = _plan(message)
    assert _facet(query, expected_code) == expected_values, message
    assert _facet(query, "shape") == ["arc"], message


PRODUCT_CODE_MIXED = [
    "EN74系列弧形会议桌",
    "EN74-2.320162 弧形会议桌",
    "弧形会议桌 EN74-2.320162 不要黑色",
]


@pytest.mark.parametrize("message", PRODUCT_CODE_MIXED)
def test_product_code_mixed_with_natural_language(message):
    query = _plan(message)
    assert _facet(query, "shape") == ["arc"], message


COMBINATION_LONG_TAIL = [
    ("实木弧形会议桌", {"shape", "material"}),
    ("玻璃弧形会议桌", {"shape", "material"}),
    ("黑色弧形会议桌", {"shape", "color"}),
    ("现代弧形会议桌", {"shape", "style"}),
    ("新中式弧形玻璃会议桌", {"shape", "style", "material"}),
]


@pytest.mark.parametrize("message, expected_codes", COMBINATION_LONG_TAIL)
def test_attribute_combinations(message, expected_codes):
    query = _plan(message)
    codes = {facet.attribute_code for facet in query.hard_facets}
    assert expected_codes <= codes, (message, codes)


UNKNOWN_LONG_TAIL = [
    "量子会议桌",
    "弧形会议桌带磁悬浮",
    "赛博朋克洽谈桌",
]


@pytest.mark.parametrize("message", UNKNOWN_LONG_TAIL)
def test_unknown_terms_are_not_silently_dropped(message):
    query = _plan(message)
    # 冷门词要么进 soft_terms，要么进 unknown_terms，但绝不能消失
    assert query.soft_terms or query.unknown_terms, message
    for term in query.soft_terms + query.unknown_terms:
        assert "弧形" not in term, (message, term)
        assert "会议桌" not in term, (message, term)


def test_unknown_term_never_becomes_hard_facet():
    query = _plan("量子会议桌")
    codes = {facet.attribute_code for facet in query.hard_facets}
    assert "quantum" not in codes
    assert all(not code.startswith("unknown") for code in codes)


# ---------------------------------------------------------------------------
# 4) 分层展示（精确 / 部分 / 文本 / 语义）
# ---------------------------------------------------------------------------


SCHEMA = (
    """
    CREATE TABLE category (
        id TEXT PRIMARY KEY, parent_id TEXT, category_name TEXT,
        sort INTEGER, level INTEGER, is_deleted BOOLEAN NOT NULL)
    """,
    """
    CREATE TABLE product (
        id TEXT PRIMARY KEY, product_no TEXT, product_name TEXT,
        brand_id TEXT, supplier_id TEXT, category_id TEXT,
        face_price FLOAT, cost_price FLOAT, material TEXT,
        stock_status TEXT, status TEXT, description TEXT,
        specification TEXT, colors TEXT, delivery_period TEXT,
        completeness_status TEXT,
        material_description TEXT, data_source TEXT, vector TEXT,
        create_time TEXT, update_time TEXT, deleted_at TEXT,
        is_deleted BOOLEAN NOT NULL)
    """,
    """
    CREATE TABLE catalog_attribute_definition (
        id TEXT PRIMARY KEY, code TEXT, name TEXT, data_type TEXT,
        multi_value BOOLEAN, searchable BOOLEAN, hard_filterable BOOLEAN,
        enabled BOOLEAN, is_deleted BOOLEAN NOT NULL)
    """,
    """
    CREATE TABLE catalog_attribute_option (
        id TEXT PRIMARY KEY, attribute_id TEXT, code TEXT, label TEXT,
        enabled BOOLEAN, is_deleted BOOLEAN NOT NULL)
    """,
    """
    CREATE TABLE product_image (
        id TEXT PRIMARY KEY, product_id TEXT, attachment_id TEXT,
        sort INTEGER, is_cover BOOLEAN, is_deleted BOOLEAN NOT NULL)
    """,
    "CREATE TABLE attachment (id TEXT PRIMARY KEY, file_name TEXT, is_deleted BOOLEAN NOT NULL)",
    """
    CREATE TABLE product_scene_image (
        id TEXT PRIMARY KEY, product_id TEXT, scene_image_id TEXT,
        sort INTEGER, is_deleted BOOLEAN NOT NULL)
    """,
    "CREATE TABLE scene_image (id TEXT PRIMARY KEY, name TEXT, is_deleted BOOLEAN NOT NULL)",
    """
    CREATE TABLE product_attribute_value (
        id TEXT PRIMARY KEY, product_id TEXT, attribute_id TEXT,
        option_id TEXT, value_text TEXT, value_num FLOAT, unit TEXT,
        source TEXT, verified BOOLEAN, confidence FLOAT,
        is_deleted BOOLEAN NOT NULL)
    """,
)

TIER_DEFINITION_ROWS = (
    ("attr-shape", "shape", "桌形", "option", 0),
    ("attr-category", "category", "类目", "option", 1),
    ("attr-color", "color", "颜色", "option", 1),
)
TIER_OPTION_ROWS = (
    ("opt-arc", "attr-shape", "arc", "弧形"),
    ("opt-rect", "attr-shape", "rect", "矩形"),
    ("opt-black", "attr-color", "black", "黑色"),
)
TIER_CATEGORY_ROWS = (
    ("c-meet", None, "会议桌", 1),
    ("c-talk", None, "洽谈桌", 1),
)
TIER_PRODUCT_ROWS = (
    # id, name, category_id, material, description, specification, colors,
    # material_description, face_price
    ("P-1", "弧形会议桌", "c-meet", "铝合金", "", "3200*1620*760", "黑色", "", 1000),
    ("P-2", "弧形洽谈桌", "c-talk", "铝合金", "", "1800*900*760", "", "", 1000),
    ("P-3", "矩形会议桌", "c-meet", "", "", "2400*1200*760", "", "", 1000),
    ("P-4", "玻璃会议桌", "c-meet", "钢化玻璃", "", "2400*1200*760", "", "", 1000),
)
TIER_VALUE_ROWS = (
    ("v-arc-1", "P-1", "attr-shape", "opt-arc", "business_confirmed", 1, 1.0),
    ("v-arc-2", "P-2", "attr-shape", "opt-arc", "business_confirmed", 1, 1.0),
    ("v-rect", "P-3", "attr-shape", "opt-rect", "business_confirmed", 1, 1.0),
    ("v-black", "P-1", "attr-color", "opt-black", "manual", 1, None),
)


def _tier_seed_statements() -> list[str]:
    statements: list[str] = []
    for row in TIER_DEFINITION_ROWS:
        statements.append(
            "INSERT INTO catalog_attribute_definition "
            "(id, code, name, data_type, multi_value, searchable, hard_filterable, "
            " enabled, is_deleted) VALUES "
            f"('{row[0]}', '{row[1]}', '{row[2]}', '{row[3]}', {row[4]}, 1, 1, 1, 0)"
        )
    for row in TIER_OPTION_ROWS:
        statements.append(
            "INSERT INTO catalog_attribute_option "
            "(id, attribute_id, code, label, enabled, is_deleted) VALUES "
            f"('{row[0]}', '{row[1]}', '{row[2]}', '{row[3]}', 1, 0)"
        )
    for row in TIER_CATEGORY_ROWS:
        parent = "NULL" if row[1] is None else f"'{row[1]}'"
        statements.append(
            "INSERT INTO category (id, parent_id, category_name, level, sort, is_deleted) "
            f"VALUES ('{row[0]}', {parent}, '{row[2]}', {row[3]}, 0, 0)"
        )
    for row in TIER_PRODUCT_ROWS:
        statements.append(
            "INSERT INTO product "
            "(id, product_no, product_name, brand_id, supplier_id, category_id, "
            " face_price, cost_price, material, stock_status, status, description, "
            " specification, colors, completeness_status, material_description, "
            " data_source, vector, create_time, update_time, deleted_at, is_deleted) "
            "VALUES "
            f"('{row[0]}', '{row[0]}', '{row[1]}', 'b', 's', '{row[2]}', {row[8]}, 900, "
            f"'{row[3]}', 'in_stock', 'active', '{row[4]}', '{row[5]}', '{row[6]}', "
            f"'complete', '{row[7]}', '', NULL, '2026-01-01', '2026-01-01', NULL, 0)"
        )
    for row in TIER_VALUE_ROWS:
        confidence = "NULL" if row[6] is None else str(row[6])
        statements.append(
            "INSERT INTO product_attribute_value "
            "(id, product_id, attribute_id, option_id, value_text, value_num, unit, "
            " source, verified, confidence, is_deleted) VALUES "
            f"('{row[0]}', '{row[1]}', '{row[2]}', '{row[3]}', NULL, NULL, NULL, "
            f"'{row[4]}', {row[5]}, {confidence}, 0)"
        )
    return statements


@pytest.fixture()
def tier_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        for statement in SCHEMA:
            connection.execute(text(statement))
        for statement in _tier_seed_statements():
            connection.execute(text(statement))
    yield engine
    engine.dispose()


def _tier_ids(engine, params: ProductSearchInput, tier: str) -> set[str]:
    statement = _build_product_search_statement(params, DICTIONARY, tier=tier)
    with engine.connect() as connection:
        return set(connection.execute(statement).scalars().all())


def test_exact_tier_requires_every_hard_facet(tier_engine):
    """exact：所有硬条件必须同时满足。"""
    params = ProductSearchInput(
        hard_facets=[
            {"attribute_code": "shape", "values": ["arc"]},
            {"attribute_code": "category", "values": ["会议桌"]},
        ]
    )
    assert _tier_ids(tier_engine, params, "exact") == {"P-1"}


def test_partial_tier_widens_the_candidate_set(tier_engine):
    """partial：工具层放宽一个条件后，候选集必须比 exact 更大。

    放宽逻辑在 ``ProductSearchTool.run``（逐个去掉硬条件再查），
    语句构建层只负责"给定条件"的语义，所以这里按工具的同样方式构造。
    """
    strict = ProductSearchInput(
        hard_facets=[
            {"attribute_code": "shape", "values": ["arc"]},
            {"attribute_code": "color", "values": ["black"]},
        ]
    )
    exact = _tier_ids(tier_engine, strict, "exact")
    relaxed_params = strict.model_copy(
        update={"hard_facets": [strict.hard_facets[0]]}
    )
    relaxed = _tier_ids(tier_engine, relaxed_params, "partial")
    assert exact == {"P-1"}
    assert relaxed - exact, "partial 必须比 exact 召回更多"


def test_match_tier_labels_are_stable():
    """分层标签必须来自固定集合（前端按 match_tier 分层展示）。"""
    import inspect

    from app.knowledge.tools import product as product_tool

    source = inspect.getsource(product_tool.ProductSearchTool.run)
    for tier in ("exact", "partial", "text_match"):
        assert f'"{tier}"' in source or f"'{tier}'" in source, tier


def test_planner_and_parser_agree_on_shape_and_negation():
    """planner 走的是同一套解析器：空格变体不改变硬条件与否定。"""
    planner = RuleBasedPlanner(dictionary=DICTIONARY)
    plan = planner.plan(KnowledgeQueryRequest(message="弧形 会议桌，不要黑色"))
    query = plan.entities.query
    assert any(
        facet.attribute_code == "shape" and facet.values == ["arc"]
        for facet in query.hard_facets
    )
    assert any(
        facet.attribute_code == "color" and facet.values == ["black"]
        for facet in query.exclude_values
    )
    # 否定词不得残留在软词里
    assert all("不要" not in term for term in query.soft_terms)


def test_planner_extracts_product_no_from_mixed_query():
    planner = RuleBasedPlanner(dictionary=DICTIONARY)
    plan = planner.plan(
        KnowledgeQueryRequest(message="弧形会议桌 EN74-2.320162 不要黑色")
    )
    query = plan.entities.query
    assert "EN74-2.320162" in query.product_nos
    assert all("EN74" not in term for term in query.soft_terms)
