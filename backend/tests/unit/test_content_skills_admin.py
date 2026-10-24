"""Track B：内容 Skills 权限与启用开关测试。

覆盖任务验收项：
* 非管理员访问管理 API 返回 403（显式 role_code 校验，不依赖 PermissionChecker）；
* 停用 Skill 不出现在选用列表；
* topic Skill 与 content Skill 不可混用；
* 默认内容 Skill 与 content_service 默认提示词等价。

SQLite 测试用裸 DDL 建表（不引入 PG 专属 UUID 类型），全部 hermetic 执行。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.api.v1 import content_skills

SKILL_TABLE = """
CREATE TABLE content_skills (
    id TEXT PRIMARY KEY,
    code TEXT, name TEXT, skill_type TEXT,
    description TEXT, prompt_template TEXT,
    output_schema TEXT, prompt_version TEXT,
    supported_platforms TEXT, enabled BOOLEAN,
    sort_order INTEGER, create_time TEXT, update_time TEXT,
    deleted_at TEXT, is_deleted BOOLEAN NOT NULL
)
"""

SEED = (
    "INSERT INTO content_skills (id, code, name, skill_type, enabled, sort_order, is_deleted) "
    "VALUES ('s-1', 'topic-basic', '基础选题', 'topic', 1, 0, 0)",
    "INSERT INTO content_skills (id, code, name, skill_type, enabled, sort_order, is_deleted) "
    "VALUES ('s-2', 'topic-off', '停用选题', 'topic', 0, 0, 0)",
    "INSERT INTO content_skills (id, code, name, skill_type, enabled, sort_order, is_deleted) "
    "VALUES ('s-3', 'content-default', '默认内容', 'content', 1, 0, 0)",
    "INSERT INTO content_skills (id, code, name, skill_type, enabled, sort_order, is_deleted) "
    "VALUES ('s-4', 'content-off', '停用内容', 'content', 0, 0, 0)",
)


@pytest.fixture()
def engine():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(SKILL_TABLE))
        for statement in SEED:
            connection.execute(text(statement))
    yield engine
    engine.dispose()


def _codes(engine, *, enabled_only=True, skill_type=None) -> set[str]:
    sql = "SELECT code FROM content_skills WHERE is_deleted = 0"
    if enabled_only:
        sql += " AND enabled = 1"
    if skill_type:
        sql += f" AND skill_type = '{skill_type}'"
    with engine.connect() as connection:
        return set(connection.execute(text(sql)).scalars().all())


# ---------------------------------------------------------------------------
# 显式 admin 校验（不能只依赖 PermissionChecker）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role_code", ["sales", "manager", "designer", "operator", "viewer", "purchaser"]
)
def test_non_admin_cannot_pass_admin_guard(role_code):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        content_skills._require_admin({"role_code": role_code})
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == 40301


def test_admin_passes_admin_guard():
    content_skills._require_admin({"role_code": "admin"})


def test_missing_role_code_is_rejected():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        content_skills._require_admin({})
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role_code", ["sales", "manager", "operator"])
def test_permission_code_alone_does_not_bypass_admin_guard(role_code):
    """持有 content:manage 权限码但角色非 admin，仍必须 403。"""
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        content_skills._require_admin(
            {"role_code": role_code, "perms": ["content:manage"]}
        )


# ---------------------------------------------------------------------------
# 启用开关
# ---------------------------------------------------------------------------


def test_disabled_skill_not_in_enabled_list(engine):
    assert _codes(engine) == {"topic-basic", "content-default"}


def test_topic_list_only_contains_topic_skills(engine):
    assert _codes(engine, skill_type="topic") == {"topic-basic"}


def test_content_list_only_contains_content_skills(engine):
    assert _codes(engine, skill_type="content") == {"content-default"}


def test_topic_skill_is_not_selectable_for_content_generation(engine):
    """内容生成只能选 content Skill；topic Skill 不可用。"""
    assert "topic-basic" not in _codes(engine, skill_type="content")


def test_content_skill_is_not_selectable_for_topic_runs(engine):
    """选题只能选 topic Skill；content Skill 不可用。"""
    assert "content-default" not in _codes(engine, skill_type="topic")


def test_disabled_skills_never_appear_in_any_list(engine):
    assert "topic-off" not in _codes(engine)
    assert "content-off" not in _codes(engine)
    assert "topic-off" not in _codes(engine, skill_type="topic")
    assert "content-off" not in _codes(engine, skill_type="content")


# ---------------------------------------------------------------------------
# 默认内容 Skill 与 content_service 默认提示词等价
# ---------------------------------------------------------------------------


def test_default_content_skill_matches_builtin_prompt():
    from app.services.content_service import PROMPT_VERSION, _build_generation_prompt

    builtin = _build_generation_prompt(
        topic="会议桌选购",
        platform="xhs",
        tone=None,
        products=[{"product_name": "弧形会议桌", "specs": "3200*1620*760", "series": "EN74"}],
    )
    assert PROMPT_VERSION == "v1"
    assert "可引用的产品事实" in builtin
    assert "禁止输出价格/折扣/交期/库存承诺" in builtin
    assert "内容需符合广告法" in builtin


def test_default_output_schema_is_preserved():
    from app.services.content_service import OUTPUT_SCHEMA

    assert OUTPUT_SCHEMA["type"] == "object"
    assert OUTPUT_SCHEMA["required"] == ["items"]
    assert OUTPUT_SCHEMA["properties"]["items"]["maxItems"] == 5
    assert OUTPUT_SCHEMA["additionalProperties"] is False


def test_content_manage_permission_seeded():
    from app.scripts.seed_data import PERMISSIONS as SEED_PERMISSIONS

    codes = {p[0] for p in SEED_PERMISSIONS}
    assert "content:manage" in codes
    # 原有内容权限未被破坏
    for code in (
        "content:view",
        "content:generate",
        "content:adopt",
        "content:publish",
        "content:metric",
    ):
        assert code in codes


def test_content_manage_permission_in_migration():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    path = root / "alembic" / "versions" / "0027_content_skills.py"
    source = path.read_text(encoding="utf-8")
    assert '"content:manage"' in source
    assert "content_topic_items" in source
    assert "content_topic_runs" in source


def test_content_manage_permission_is_mapped_to_admin_in_migration():
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    path = root / "alembic" / "versions" / "0027_content_skills.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mapping = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ROLE_PERMISSION_MAP":
                    mapping = ast.literal_eval(node.value)
                    break
    assert mapping is not None
    assert mapping["admin"] == ["content:manage"]
