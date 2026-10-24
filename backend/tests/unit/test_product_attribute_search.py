"""Track A：受治理属性检索的结构化 SQL 层测试。

覆盖任务验收项：
* 属性缺失不算命中（只有 material/description 文本含"弧形"的普通会议桌
  不会作为 exact 命中；
* style 标签不能替代 shape 属性；
* 不同属性 AND、同属性同义词 OR、match_mode=all；
* 否定条件（排除圆形）形成过滤；
* 数值条件形成过滤；
* 旧 facets dict 仍被兼容接收，但不引入新维度。

全部用裸 SQLite DDL 建表（不引入 PG 专属 UUID 类型），
作为 hermetic 单测执行，不连任何数据库。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.knowledge.tools.product import (
    ProductSearchInput,
    _build_product_search_statement,
)

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
        specification TEXT, colors TEXT, completeness_status TEXT,
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
    # _base_product_stmt() 需要的关系表
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

SHAPE = "attr-shape"
CATEGORY = "attr-category"
COLOR = "attr-color"

SHAPE = "attr-shape"
CATEGORY = "attr-category"
COLOR = "attr-color"

# 属性定义：code 与生产词典一致
DEFINITION_ROWS = (
    ("attr-shape", "shape", "桌形", "option", 0),
    ("attr-category", "category", "类目", "option", 1),
    ("attr-color", "color", "颜色", "option", 1),
)
# 属性取值：id, attribute_id, code, label
OPTION_ROWS = (
    ("opt-arc", "attr-shape", "arc", "弧形"),
    ("opt-rect", "attr-shape", "rect", "矩形"),
    ("opt-round", "attr-shape", "round", "圆形"),
    ("opt-black", "attr-color", "black", "黑色"),
    ("opt-white", "attr-color", "white", "白色"),
)
# 类目树：会议桌 <- 经理会议桌（子孙也应命中）；另有洽谈桌
CATEGORY_ROWS = (
    ("c-meet", None, "会议桌", 1),
    ("c-meet-leaf", "c-meet", "经理会议桌", 2),
    ("c-talk", None, "洽谈桌", 1),
)
# 产品：id, name, category_id, material, description, specification, colors,
#       material_description, face_price
PRODUCT_ROWS = (
    ("P-1", "弧形会议桌", "c-meet", "铝合金下脚弧型会议桌", "", "3200*1620*760",
     "胡桃木", "弧型台面", 1000),
    # material/description 里出现"弧形"，但没有 shape 属性 -> 不得作为 exact
    ("P-2", "普通会议桌", "c-meet", "弧型桌腿说明", "弧形桌边", "3000*1500*760",
     "", "", 1000),
    # 弧形 + 洽谈桌（category 也是洽谈桌）
    ("P-3", "弧形洽谈桌", "c-talk", "弧型", "", "1800*900*760", "", "", 1000),
    # 仅有 style 标签写"弧形"（用 shape 缺失表达：不得作为 exact）
    ("P-4", "新中式会议桌", "c-meet", "", "弧形", "", "", "", 1000),
    ("P-5", "矩形会议桌", "c-meet", "", "", "2400*1200*760", "", "", 1000),
    ("P-6", "圆形会议桌", "c-meet", "", "", "1600*1600*760", "", "", 1000),
    ("P-7", "双色会议桌", "c-meet", "", "", "2000*1000*760", "", "", 1000),
    ("P-8", "加长会议桌", "c-meet", "", "", "6000*1600*760", "", "", 1000),
)
# 属性值：id, product_id, attribute_id, option_id, source, verified, confidence
VALUE_ROWS = (
    ("v-arc", "P-1", "attr-shape", "opt-arc", "business_confirmed", 1, 1.0),
    ("v-arc-talk", "P-3", "attr-shape", "opt-arc", "business_confirmed", 1, 1.0),
    ("v-rect", "P-5", "attr-shape", "opt-rect", "business_confirmed", 1, 1.0),
    ("v-round", "P-6", "attr-shape", "opt-round", "business_confirmed", 1, 1.0),
    ("v-bw-1", "P-7", "attr-color", "opt-black", "manual", 1, None),
    ("v-bw-2", "P-7", "attr-color", "opt-white", "manual", 1, None),
)


def _seed_statements() -> list[str]:
    statements: list[str] = []
    for row in DEFINITION_ROWS:
        statements.append(
            "INSERT INTO catalog_attribute_definition "
            "(id, code, name, data_type, multi_value, searchable, hard_filterable, "
            " enabled, is_deleted) VALUES "
            f"('{row[0]}', '{row[1]}', '{row[2]}', '{row[3]}', {row[4]}, 1, 1, 1, 0)"
        )
    for row in OPTION_ROWS:
        statements.append(
            "INSERT INTO catalog_attribute_option "
            "(id, attribute_id, code, label, enabled, is_deleted) VALUES "
            f"('{row[0]}', '{row[1]}', '{row[2]}', '{row[3]}', 1, 0)"
        )
    for row in CATEGORY_ROWS:
        parent = "NULL" if row[1] is None else f"'{row[1]}'"
        statements.append(
            "INSERT INTO category (id, parent_id, category_name, level, sort, is_deleted) "
            f"VALUES ('{row[0]}', {parent}, '{row[2]}', {row[3]}, 0, 0)"
        )
    for row in PRODUCT_ROWS:
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
    for row in VALUE_ROWS:
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
def engine():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        for statement in SCHEMA:
            connection.execute(text(statement))
        for statement in _seed_statements():
            connection.execute(text(statement))
    yield engine
    engine.dispose()


def _ids(engine, params: ProductSearchInput) -> set[str]:
    statement = _build_product_search_statement(params, _dictionary())
    with engine.connect() as connection:
        return set(connection.execute(statement).scalars().all())


def _dictionary():
    from app.knowledge.attributes import (
        EMPTY_DICTIONARY,
        AttributeDefinitionView,
        AttributeDictionary,
    )
    if EMPTY_DICTIONARY.definitions:
        return EMPTY_DICTIONARY
    definitions = {
        "shape": AttributeDefinitionView(
            code="shape", name="桌形", data_type="option",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
        "category": AttributeDefinitionView(
            code="category", name="类目", data_type="option",
            multi_value=True, searchable=True, hard_filterable=True,
        ),
        "color": AttributeDefinitionView(
            code="color", name="颜色", data_type="option",
            multi_value=True, searchable=True, hard_filterable=True,
        ),
        "face_price": AttributeDefinitionView(
            code="face_price", name="面价", data_type="number",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
        "specification_length_mm": AttributeDefinitionView(
            code="specification_length_mm", name="长度", data_type="number",
            multi_value=False, searchable=True, hard_filterable=True,
        ),
    }
    return AttributeDictionary(definitions=definitions, aliases=[])


def test_arc_shape_matches_only_governed_products(engine):
    ids = _ids(
        engine,
        ProductSearchInput(hard_facets=[{"attribute_code": "shape", "values": ["arc"]}]),
    )
    # 不含 p-plain / p-style：它们没有任何 shape 属性取值
    assert ids == {'P-1', 'P-3'}


def test_arc_meeting_table_requires_shape_and_category(engine):
    ids = _ids(
        engine,
        ProductSearchInput(
            hard_facets=[
                {"attribute_code": "shape", "values": ["arc"]},
                {"attribute_code": "category", "values": ["会议桌"]},
            ]
        ),
    )
    assert ids == {'P-1'}


def test_material_text_alone_is_not_a_shape_hit(engine):
    ids = _ids(
        engine,
        ProductSearchInput(hard_facets=[{"attribute_code": "shape", "values": ["arc"]}]),
    )
    assert "P-2" not in ids
    assert "P-4" not in ids


def test_synonyms_are_or_within_one_attribute(engine):
    ids = _ids(
        engine,
        ProductSearchInput(hard_facets=[{"attribute_code": "shape", "values": ["arc", "rect"]}]),
    )
    assert ids == {'P-1', 'P-3', 'P-5'}


def test_match_mode_all_requires_every_value(engine):
    ids = _ids(
        engine,
        ProductSearchInput(
            hard_facets=[
                {"attribute_code": "color", "values": ["black", "white"], "match_mode": "all"}
            ]
        ),
    )
    assert ids == {'P-7'}


def test_exclude_values_filters_a_shape(engine):
    ids = _ids(
        engine,
        ProductSearchInput(
            hard_facets=[{"attribute_code": "category", "values": ["会议桌"]}],
            exclude_values=[{"attribute_code": "shape", "values": ["round", "rect"]}],
        ),
    )
    # 会议桌下排除矩形与圆形 -> 只剩弧形/普通/双色/加长（无 shape 的不被排除）
    assert "P-6" not in ids
    assert "P-5" not in ids
    assert "P-1" in ids

def test_numeric_filters_form_real_filters(engine):
    ids = _ids(
        engine,
        ProductSearchInput(numeric_filters=[{"attribute_code": "face_price", "max_value": 500}]),
    )
    assert ids == set()
    ids = _ids(
        engine,
        ProductSearchInput(numeric_filters=[{"attribute_code": "face_price", "min_value": 1000}]),
    )
    assert ids == {'P-1', 'P-2', 'P-3', 'P-4', 'P-5', 'P-6', 'P-7', 'P-8'}


def test_length_filter_uses_specification_column(engine):
    ids = _ids(
        engine,
        ProductSearchInput(
            numeric_filters=[
                {"attribute_code": "specification_length_mm", "min_value": 5000}
            ]
        ),
    )
    assert ids == {'P-8'}


def test_legacy_facets_dict_is_coerced(engine):
    params = ProductSearchInput(facets={"shape": ["arc"], "category": ["会议桌"]})
    assert sorted(f.attribute_code for f in params.hard_facets) == ["category", "shape"]
    ids = _ids(engine, params)
    assert ids == {'P-1'}


def test_facets_model_is_generic():
    from app.knowledge.facets import ProductFacets

    facets = ProductFacets(values={"shape": ["arc"], "style": ["modern"]})
    assert facets.shape == ["arc"]
    assert facets.category == []
    assert facets.has_constraints()


def test_empty_dictionary_does_not_infer_hard_facets():
    from app.knowledge.attributes import EMPTY_DICTIONARY, build_product_query

    query = build_product_query("弧形会议桌", EMPTY_DICTIONARY)
    assert query.hard_facets == []
    assert query.numeric_filters == []


def test_populated_dictionary_drives_hard_facet_query():
    from app.knowledge.attributes import (
        AliasEntry,
        AttributeDefinitionView,
        AttributeDictionary,
        build_product_query,
    )

    dictionary = AttributeDictionary(
        definitions={
            "shape": AttributeDefinitionView(
                code="shape", name="桌形", data_type="option", multi_value=False,
                searchable=True, hard_filterable=True,
            )
        },
        aliases=[AliasEntry("shape", "arc", "弧形", "弧形")],
    )
    query = build_product_query("弧形", dictionary)

    assert len(query.hard_facets) == 1
    assert query.hard_facets[0].attribute_code == "shape"
    assert query.hard_facets[0].values == ["arc"]
