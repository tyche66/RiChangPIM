"""Focused proposal-space tests that do not require a database connection."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.proposals import _enrich_item, _resolve_item_space
from app.api.v1.share_token import _space_labels


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def first(self):
        return self.value


class _NoDb:
    async def execute(self, _statement):
        raise AssertionError("unscoped labels must not query project spaces")


class _RowsDb:
    def __init__(self, *values):
        self.values = list(values)

    async def execute(self, _statement):
        return _Result(self.values.pop(0))


class _CreationDb(_RowsDb):
    def __init__(self, *values):
        super().__init__(*values)
        self.added = []

    def add(self, value):
        if value.id is None:
            value.id = uuid4()
        self.added.append(value)

    async def flush(self):
        return None


@pytest.mark.anyio
async def test_unscoped_labels_are_saved_without_project_space_id():
    item = SimpleNamespace(
        project_space_id=uuid4(),
        floor_label="  9F ",
        space_label=" 新会议室 ",
    )

    resolved = await _resolve_item_space(item, None, _NoDb())

    assert resolved == {
        "project_space_id": None,
        "floor_label": "9F",
        "space_label": "新会议室",
    }


@pytest.mark.anyio
async def test_existing_project_labels_reuse_nodes():
    project_id = uuid4()
    floor_id = uuid4()
    room_id = uuid4()
    floor = SimpleNamespace(
        id=floor_id,
        project_id=project_id,
        space_type="floor",
        space_name="9F",
    )
    room = SimpleNamespace(
        id=room_id,
        project_id=project_id,
        space_type="room",
        space_name="新会议室",
    )
    db = _RowsDb(project_id, floor, room)
    item = SimpleNamespace(
        project_space_id=None,
        floor_label="9F",
        space_label="新会议室",
    )

    resolved = await _resolve_item_space(item, project_id, db)

    assert resolved == {
        "project_space_id": room_id,
        "floor_label": "9F",
        "space_label": "新会议室",
    }


@pytest.mark.anyio
async def test_label_only_item_creates_project_scoped_nodes():
    project_id = uuid4()
    db = _CreationDb(project_id, None, None)
    item = SimpleNamespace(
        project_space_id=None,
        floor_label=" 9F ",
        space_label=" 新会议室 ",
    )

    resolved = await _resolve_item_space(item, project_id, db)

    assert resolved["floor_label"] == "9F"
    assert resolved["space_label"] == "新会议室"
    assert resolved["project_space_id"] == db.added[-1].id
    assert [space.space_name for space in db.added] == ["9F", "新会议室"]
    assert all(space.project_id == project_id for space in db.added)


@pytest.mark.anyio
async def test_existing_project_space_id_is_retained_and_can_echo_labels():
    project_id = uuid4()
    space_id = uuid4()
    existing = SimpleNamespace(
        id=space_id,
        project_id=project_id,
        space_type="room",
        space_name="会议室",
        parent=SimpleNamespace(space_type="floor", space_name="9F"),
    )
    db = _RowsDb(project_id, existing)
    item = SimpleNamespace(project_space_id=space_id, floor_label=None, space_label=None)

    resolved = await _resolve_item_space(item, project_id, db)

    assert resolved["project_space_id"] == space_id
    assert resolved["floor_label"] == "9F"
    assert resolved["space_label"] == "会议室"


@pytest.mark.anyio
async def test_cross_project_space_id_is_rejected():
    project_id = uuid4()
    other_project_id = uuid4()
    existing = SimpleNamespace(
        id=uuid4(),
        project_id=other_project_id,
        space_type="room",
        space_name="外部会议室",
    )
    db = _RowsDb(project_id, existing)
    item = SimpleNamespace(
        project_space_id=existing.id,
        floor_label="3F",
        space_label="外部会议室",
    )

    with pytest.raises(HTTPException) as error:
        await _resolve_item_space(item, project_id, db)

    assert error.value.status_code == 422
    assert "不属于方案关联项目" in str(error.value.detail)


def test_existing_binding_echoes_floor_and_space_on_read():
    item = SimpleNamespace(
        id=uuid4(),
        product_id=uuid4(),
        product_snapshot=None,
        quantity=1,
        remark=None,
        project_space_id=uuid4(),
        floor_label=None,
        space_label=None,
        material_desc=None,
        space=SimpleNamespace(
            space_type="room",
            space_name="会议室",
            parent=SimpleNamespace(space_type="floor", space_name="9F"),
        ),
    )

    enriched = _enrich_item(item, None, None)

    assert enriched["project_space_id"] == str(item.project_space_id)
    assert enriched["floor_label"] == "9F"
    assert enriched["space_label"] == "会议室"


def test_share_payload_echoes_existing_binding_labels():
    item = SimpleNamespace(
        floor_label=None,
        space_label=None,
        space=SimpleNamespace(
            space_type="room",
            space_name="会议室",
            parent=SimpleNamespace(space_type="floor", space_name="9F"),
        ),
    )

    assert _space_labels(item) == ("9F", "会议室")
