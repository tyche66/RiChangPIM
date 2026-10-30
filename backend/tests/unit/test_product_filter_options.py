"""六维度筛选选项：二级/三级的数据来源与口径。

用裸 SQLite DDL 建最小表结构（不连库、不依赖 aiosqlite），
把「选项从产品数据实时聚合」这条规则钉死：

* 没有产品的分类 / 品牌 / 标签不出现；
* 分类计数含后代，和列表筛选（含后代）对得上；
* 「系列」三级只认 series 标签，「品类」三级解析规格第一段；
* 同名二级分类在两个维度下各取各的三级数据。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.services.product_filter_options import (
    FilterOptionError,
    list_filter_options,
    specification_values_for,
)
from app.services.specification import parse_spec_length_mm

SCHEMA = (
    """
    CREATE TABLE category (
        id TEXT PRIMARY KEY, parent_id TEXT, category_name TEXT,
        sort INTEGER, level INTEGER, is_deleted BOOLEAN NOT NULL)
    """,
    "CREATE TABLE brand (id TEXT PRIMARY KEY, brand_name TEXT, is_deleted BOOLEAN NOT NULL)",
    "CREATE TABLE supplier (id TEXT PRIMARY KEY, supplier_name TEXT, is_deleted BOOLEAN NOT NULL)",
    """
    CREATE TABLE tag (
        id TEXT PRIMARY KEY, tag_name TEXT, tag_type TEXT,
        is_deleted BOOLEAN NOT NULL)
    """,
    """
    CREATE TABLE product (
        id TEXT PRIMARY KEY, product_no TEXT, product_name TEXT,
        brand_id TEXT, supplier_id TEXT, category_id TEXT,
        face_price FLOAT, cost_price FLOAT, material TEXT,
        stock_status TEXT, status TEXT, description TEXT,
        specification TEXT, colors TEXT, delivery_period TEXT,
        completeness_status TEXT, material_description TEXT, data_source TEXT,
        vector TEXT, create_time TEXT, update_time TEXT, deleted_at TEXT,
        is_deleted BOOLEAN NOT NULL)
    """,
    """
    CREATE TABLE product_tag (
        product_id TEXT, tag_id TEXT, is_deleted BOOLEAN NOT NULL)
    """,
)

C1, C2, C3, C4 = (uuid4() for _ in range(4))
B1, B2 = (uuid4() for _ in range(2))
S1, S2 = (uuid4() for _ in range(2))
T1, T2, T3 = (uuid4() for _ in range(3))
P1, P2, P3, P4, P5 = (uuid4() for _ in range(5))

CATEGORIES = (
    (C1, None, "办公家具"),
    (C2, C1, "办公桌"),
    (C3, C1, "会议桌"),
    (C4, C1, "办公椅"),
)
BRANDS = ((B1, "品牌甲"), (B2, "品牌乙"))
SUPPLIERS = ((S1, "供应商甲"), (S2, "供应商乙"))
TAGS = ((T1, "大都会", "series"), (T3, "瓦尔纳", "series"), (T2, "新中式", "style"))
# id, category, brand, supplier, status, stock, specification, is_deleted
PRODUCTS = (
    (P1, C2, B1, S1, "active", "in_stock", "1800*900*750", 0),
    # 真实库里 W 前缀与纯数字混用，解析必须一视同仁。
    (P2, C2, B1, S2, "inactive", "out_of_stock", "W2200*1000*750", 0),
    (P3, C3, B2, S1, "active", "in_stock", "1200*600*750", 0),
    (P4, C4, B2, S2, "draft", "unknown", None, 0),
    (P5, C2, B1, S1, "active", "in_stock", "1800*900*750", 1),
)
PRODUCT_TAGS = ((P1, T1), (P2, T1), (P3, T3), (P1, T2), (P5, T1))


class _AsyncDb:
    """把同步 SQLite 连接包成服务需要的 async execute。"""

    def __init__(self, connection):
        self.connection = connection

    async def execute(self, stmt):
        return self.connection.execute(stmt)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        for ddl in SCHEMA:
            connection.execute(text(ddl))
        for row in CATEGORIES:
            connection.execute(
                text(
                    "INSERT INTO category (id, parent_id, category_name, is_deleted) "
                    "VALUES (:id, :parent_id, :category_name, 0)"
                ),
                {
                    "id": row[0].hex,
                    "parent_id": row[1].hex if row[1] else None,
                    "category_name": row[2],
                },
            )
        for ident, name in BRANDS:
            connection.execute(
                text("INSERT INTO brand (id, brand_name, is_deleted) VALUES (:i, :n, 0)"),
                {"i": ident.hex, "n": name},
            )
        for ident, name in SUPPLIERS:
            connection.execute(
                text("INSERT INTO supplier (id, supplier_name, is_deleted) VALUES (:i, :n, 0)"),
                {"i": ident.hex, "n": name},
            )
        for ident, name, tag_type in TAGS:
            connection.execute(
                text("INSERT INTO tag (id, tag_name, tag_type, is_deleted) VALUES (:i, :n, :t, 0)"),
                {"i": ident.hex, "n": name, "t": tag_type},
            )
        for ident, cat, brand, supplier, status, stock, spec, deleted in PRODUCTS:
            connection.execute(
                text(
                    "INSERT INTO product (id, category_id, brand_id, supplier_id, status, "
                    "stock_status, specification, is_deleted) VALUES "
                    "(:i, :c, :b, :s, :st, :stock, :spec, :d)"
                ),
                {
                    "i": ident.hex,
                    "c": cat.hex,
                    "b": brand.hex,
                    "s": supplier.hex,
                    "st": status,
                    "stock": stock,
                    "spec": spec,
                    "d": deleted,
                },
            )
        for product_id, tag_id in PRODUCT_TAGS:
            connection.execute(
                text("INSERT INTO product_tag (product_id, tag_id, is_deleted) VALUES (:p, :t, 0)"),
                {"p": product_id.hex, "t": tag_id.hex},
            )
        yield _AsyncDb(connection)


def _values(items):
    return [item["value"] for item in items]


def _by_value(items):
    return {item["value"]: item for item in items}


@pytest.mark.asyncio
async def test_series_level2_lists_categories_with_series_tags_and_direct_counts(db):
    items = await list_filter_options(db, dimension="series")
    values = _values(items)
    # 办公椅下没有带 series 标签的产品，不出现。
    assert str(C4) not in values
    counts = {item["value"]: item["count"] for item in items}
    assert counts[str(C2)] == 2
    assert counts[str(C3)] == 1
    # 一级分类的计数含后代：办公家具 = 办公桌 2 + 会议桌 1。
    assert counts[str(C1)] == 3
    assert values[0] == str(C1)


@pytest.mark.asyncio
async def test_series_level3_only_series_tags_in_category_scope(db):
    items = await list_filter_options(db, dimension="series", parent_id=str(C1))
    assert [item["label"] for item in items] == ["大都会", "瓦尔纳"]
    assert _by_value(items)[str(T1)]["count"] == 2

    narrowed = await list_filter_options(db, dimension="series", parent_id=str(C2))
    assert _values(narrowed) == [str(T1)]

    empty = await list_filter_options(db, dimension="series", parent_id=str(C4))
    assert empty == []


@pytest.mark.asyncio
async def test_category_level2_counts_ignore_tags(db):
    items = await list_filter_options(db, dimension="category")
    counts = {item["value"]: item["count"] for item in items}
    assert counts == {str(C1): 4, str(C2): 2, str(C3): 1, str(C4): 1}
    assert items[0]["value"] == str(C1)


@pytest.mark.asyncio
async def test_category_level3_reads_specification_length(db):
    items = await list_filter_options(db, dimension="category", parent_id=str(C1))
    assert [item["label"] for item in items] == ["1200", "1800", "2200"]
    # 已软删除的 P5 也是 1800，但不计入——菜单计数必须和列表能查到的数量一致。
    assert _by_value(items)["1800"]["count"] == 1

    # 同一个「办公桌」在系列维度下给的是系列标签，不是规格——两套三级互不串数据。
    series_items = await list_filter_options(db, dimension="series", parent_id=str(C2))
    assert [item["label"] for item in series_items] == ["大都会"]


@pytest.mark.asyncio
async def test_brand_and_supplier_levels(db):
    brands = await list_filter_options(db, dimension="brand")
    assert {item["value"]: item["count"] for item in brands} == {str(B1): 2, str(B2): 2}

    brand_categories = await list_filter_options(db, dimension="brand", parent_id=str(B1))
    assert [(item["value"], item["count"]) for item in brand_categories] == [(str(C2), 2)]

    suppliers = await list_filter_options(db, dimension="supplier")
    assert {item["value"]: item["count"] for item in suppliers} == {str(S1): 2, str(S2): 2}

    supplier_categories = await list_filter_options(
        db, dimension="supplier", parent_id=str(S1)
    )
    assert {item["value"]: item["count"] for item in supplier_categories} == {
        str(C2): 1,
        str(C3): 1,
    }


@pytest.mark.asyncio
async def test_status_and_stock_are_flat_with_business_labels(db):
    statuses = await list_filter_options(db, dimension="status")
    assert {item["value"]: item["label"] for item in statuses} == {
        "active": "上架",
        "inactive": "下架",
        "draft": "草稿",
    }
    stocks = await list_filter_options(db, dimension="stock")
    assert _by_value(stocks)["in_stock"]["label"] == "有货"

    # 枚举维度没有三级：即使传 parent_id 也返回同一份二级列表。
    assert await list_filter_options(db, dimension="status", parent_id=str(C1)) == statuses


@pytest.mark.asyncio
async def test_invalid_dimension_and_parent_raise(db):
    with pytest.raises(FilterOptionError):
        await list_filter_options(db, dimension="unknown")
    with pytest.raises(FilterOptionError):
        await list_filter_options(db, dimension="series", parent_id="not-a-uuid")
    # 需要三级数据的维度省略 parent_id 时返回二级，而不是报错。
    assert await list_filter_options(db, dimension="series", parent_id=None)


def test_parse_spec_length_handles_prefixes_and_garbage():
    assert parse_spec_length_mm("1200*600*750") == 1200
    assert parse_spec_length_mm("W2000*1000*750") == 2000
    assert parse_spec_length_mm("L1000") == 1000
    assert parse_spec_length_mm("异形") is None
    assert parse_spec_length_mm("/") is None
    assert parse_spec_length_mm(None) is None


@pytest.mark.asyncio
async def test_specification_values_roundtrip_for_filtering(db):
    # 菜单上的 2200 要能还原成库里真实的写法（这里带 W 前缀），否则点进去查不到。
    assert await specification_values_for(db, 2200) == ["W2200*1000*750"]
    assert await specification_values_for(db, 1800) == ["1800*900*750"]
    assert await specification_values_for(db, 9999) == []
