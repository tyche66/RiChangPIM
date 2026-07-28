from __future__ import annotations

from types import SimpleNamespace

from app.knowledge.source_access import can_access_document


def _document(**overrides):
    data = {
        'is_active': True,
        'is_deleted': False,
        'visibility': 'internal',
        'required_permission': None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_admin_can_access_restricted_document():
    assert can_access_document(_document(visibility='private'), {'role_code': 'admin', 'perms': []})


def test_viewer_cannot_access_private_document():
    assert not can_access_document(_document(visibility='private'), {'role_code': 'viewer', 'perms': []})


def test_required_permission_is_enforced():
    doc = _document(required_permission='knowledge:debug')
    assert not can_access_document(doc, {'role_code': 'viewer', 'perms': ['ai:knowledge']})
    assert can_access_document(doc, {'role_code': 'viewer', 'perms': ['knowledge:debug']})
