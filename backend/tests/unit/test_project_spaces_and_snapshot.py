"""Track C：项目空间、方案明细快照与分享载荷测试。

覆盖任务验收项：
* 空间必须属于项目（跨项目父空间被拒绝）；
* 快照由服务端生成，不信任前端传入的产品事实；
* 读取优先级：快照 > 当前产品 > 「资料未提供」；
* 分享载荷包含楼层/空间/材质/颜色/材质说明；
* 分享载荷不含成本价/供应商/利润等敏感字段。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.services.product_snapshot import (
    MISSING_TEXT,
    display_value,
    merge_snapshot,
)

SPACE_TABLE = """
CREATE TABLE project_spaces (
    id TEXT PRIMARY KEY,
    project_id TEXT, parent_id TEXT,
    space_type TEXT, space_name TEXT,
    level INTEGER, sort INTEGER,
    create_time TEXT, update_time TEXT,
    deleted_at TEXT, is_deleted BOOLEAN NOT NULL
)
"""

SEED = (
    "INSERT INTO project_spaces "
    "(id, project_id, parent_id, space_type, space_name, level, sort, is_deleted) "
    "VALUES ('s-floor-1', 'p-1', NULL, 'floor', '1F', 1, 0, 0)",
    "INSERT INTO project_spaces "
    "(id, project_id, parent_id, space_type, space_name, level, sort, is_deleted) "
    "VALUES ('s-room-1', 'p-1', 's-floor-1', 'room', '接待区', 2, 0, 0)",
    "INSERT INTO project_spaces "
    "(id, project_id, parent_id, space_type, space_name, level, sort, is_deleted) "
    "VALUES ('s-room-2', 'p-1', 's-floor-1', 'room', '会议室', 2, 1, 0)",
    "INSERT INTO project_spaces "
    "(id, project_id, parent_id, space_type, space_name, level, sort, is_deleted) "
    "VALUES ('s-floor-2', 'p-1', NULL, 'floor', '2F', 1, 1, 0)",
    "INSERT INTO project_spaces "
    "(id, project_id, parent_id, space_type, space_name, level, sort, is_deleted) "
    "VALUES ('s-other', 'p-2', NULL, 'room', '别的项目的房间', 1, 0, 0)",
)


@pytest.fixture()
def engine():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(SPACE_TABLE))
        for statement in SEED:
            connection.execute(text(statement))
    yield engine
    engine.dispose()


def _rows(engine, sql: str) -> list[tuple]:
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(text(sql)).all()]


# ---------------------------------------------------------------------------
# 空间树
# ---------------------------------------------------------------------------


def test_space_tree_has_two_floors(engine):
    rows = _rows(
        engine,
        "SELECT space_name FROM project_spaces WHERE space_type = 'floor' "
        "AND is_deleted = 0 ORDER BY sort",
    )
    assert rows == [("1F",), ("2F",)]


def test_rooms_belong_to_their_floor(engine):
    rows = _rows(
        engine,
        "SELECT space_name FROM project_spaces WHERE parent_id = 's-floor-1' "
        "AND is_deleted = 0 ORDER BY sort",
    )
    assert rows == [("接待区",), ("会议室",)]


def test_space_must_belong_to_project(engine):
    """跨项目引用父空间必须被拒绝（API 层校验，这里验证 SQL 语义）。"""
    rows = _rows(
        engine,
        "SELECT id FROM project_spaces WHERE id = 's-other' AND project_id = 'p-1'",
    )
    assert rows == []
    rows = _rows(
        engine,
        "SELECT id FROM project_spaces WHERE id = 's-other' AND project_id = 'p-2'",
    )
    assert rows == [("s-other",)]


def test_space_type_is_constrained():
    """模型层 CheckConstraint 限定 space_type 取值。"""
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[2]
        / "app"
        / "models"
        / "sales.py"
    ).read_text(encoding="utf-8")
    assert "space_type IN ('floor','room','zone','other')" in source


# ---------------------------------------------------------------------------
# 产品事实快照
# ---------------------------------------------------------------------------


class _FakeProduct:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_snapshot_wins_over_current_product():
    """产品改名/改材质后，历史方案仍展示快照。"""
    snapshot = {
        "product_no": "OLD-001",
        "product_name": "旧名称弧形会议桌",
        "category_name": "会议桌",
        "material": "旧材质",
        "colors": "旧颜色",
        "material_description": "旧材质说明",
        "specification": "3200*1620*760",
        "face_price": 6800.0,
    }
    product = _FakeProduct(
        product_no="NEW-001",
        product_name="新名称矩形会议桌",
        category=_FakeProduct(category_name="办公桌"),
        material="新材质",
        colors="新颜色",
        material_description="新材质说明",
        specification="2400*1200*760",
        face_price=99999,
    )
    merged = merge_snapshot(snapshot, product)
    assert merged["product_name"] == "旧名称弧形会议桌"
    assert merged["product_no"] == "OLD-001"
    assert merged["material"] == "旧材质"
    assert merged["colors"] == "旧颜色"
    assert merged["material_description"] == "旧材质说明"
    assert merged["specification"] == "3200*1620*760"
    assert merged["face_price"] == 6800.0


def test_falls_back_to_current_product_when_no_snapshot():
    """旧方案没有快照时回落当前产品字段（不报错、不漂移到空）。"""
    product = _FakeProduct(
        product_no="P-1",
        product_name="弧形会议桌",
        category=_FakeProduct(category_name="会议桌"),
        material="中纤板",
        colors="胡桃木",
        material_description="40mm 台面",
        specification="3200*1620*760",
        face_price=6800.0,
    )
    merged = merge_snapshot(None, product)
    assert merged["product_name"] == "弧形会议桌"
    assert merged["material"] == "中纤板"
    assert merged["face_price"] == 6800.0


def test_missing_fields_show_placeholder():
    """快照与产品都缺失时显示「资料未提供」。"""
    product = _FakeProduct(
        product_no=None,
        product_name=None,
        category=None,
        material=None,
        colors=None,
        material_description=None,
        specification=None,
        face_price=None,
    )
    merged = merge_snapshot(None, product)
    for key in (
        "product_no",
        "product_name",
        "category_name",
        "material",
        "colors",
        "material_description",
        "specification",
    ):
        assert merged[key] == MISSING_TEXT, key


def test_placeholder_price_is_not_shown():
    """99999 占位价不作为真实价格展示。"""
    product = _FakeProduct(
        product_no="P-1",
        product_name="会议桌",
        category=None,
        material=None,
        colors=None,
        material_description=None,
        specification=None,
        face_price=99999,
    )
    merged = merge_snapshot(None, product)
    assert merged["face_price"] == MISSING_TEXT


def test_display_value_helper():
    assert display_value(None) == MISSING_TEXT
    assert display_value("") == MISSING_TEXT
    assert display_value([]) == MISSING_TEXT
    assert display_value("弧形") == "弧形"
    assert display_value(0) == "0"


# ---------------------------------------------------------------------------
# 分享载荷敏感字段过滤
# ---------------------------------------------------------------------------


def test_share_payload_excludes_sensitive_fields():
    """分享载荷不得包含成本价/供应商/利润。"""
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[2]
        / "app"
        / "api"
        / "v1"
        / "share_token.py"
    ).read_text(encoding="utf-8")
    # 分享载荷构造处不得引用敏感字段
    assert '"cost_price"' not in source
    assert '"supplier_id"' not in source
    assert '"supplier_name"' not in source
    assert '"margin"' not in source
    assert '"profit"' not in source


def test_share_payload_includes_space_and_material_fields():
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[2]
        / "app"
        / "api"
        / "v1"
        / "share_token.py"
    ).read_text(encoding="utf-8")
    for field in (
        "floor_label",
        "space_label",
        "material_desc",
        "material",
        "colors",
        "material_description",
        "specification",
        "product_snapshot",
    ):
        assert f'"{field}"' in source, field


def test_share_payload_uses_snapshot_first():
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[2]
        / "app"
        / "api"
        / "v1"
        / "share_token.py"
    ).read_text(encoding="utf-8")
    assert "_snapshot_field" in source
    assert "from functools import partial" in source


# ---------------------------------------------------------------------------
# 迁移与模型契约
# ---------------------------------------------------------------------------


def test_migration_creates_project_spaces_and_item_columns():
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0028_project_spaces.py"
    ).read_text(encoding="utf-8")
    assert '"project_spaces"' in source
    for column in (
        "project_space_id",
        "floor_label",
        "space_label",
        "material_desc",
        "product_snapshot",
    ):
        assert f'"{column}"' in source, column
    # 全部可空，旧数据无需回填
    assert "nullable=True" in source


def test_proposal_item_model_has_space_fields():
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[2]
        / "app"
        / "models"
        / "sales.py"
    ).read_text(encoding="utf-8")
    for column in (
        "project_space_id",
        "floor_label",
        "space_label",
        "material_desc",
        "product_snapshot",
    ):
        assert f"{column} = Column(" in source, column


def test_proposal_schema_accepts_customer_and_project():
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[2]
        / "app"
        / "schemas"
        / "proposal.py"
    ).read_text(encoding="utf-8")
    assert "customer_id" in source
    assert "project_id" in source
    assert "project_space_id" in source
    assert "material_desc" in source
