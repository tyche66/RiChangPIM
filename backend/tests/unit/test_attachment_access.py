"""Unit tests for attachment access control (HLD §4.8).

Tests can_access_attachment with mock user/attachment objects.
"""

from types import SimpleNamespace
from uuid import uuid4

from app.core.attachment_access import can_access_attachment


def _make_user(role_code="sales", permissions=None, visible_customer_ids=None, visible_project_ids=None):
    """Create a mock user object."""
    return SimpleNamespace(
        role_code=role_code,
        permissions=permissions or [],
        visible_customer_ids=visible_customer_ids,
        visible_project_ids=visible_project_ids,
    )


def _make_attachment(biz_domain=None, biz_scope_id=None):
    """Create a mock attachment object."""
    return SimpleNamespace(
        biz_domain=biz_domain,
        biz_scope_id=biz_scope_id,
    )


class TestAttachmentAccess:
    """Attachment access control tests."""

    def test_biz_domain_none(self):
        """biz_domain=None -> True (product files)."""
        user = _make_user()
        att = _make_attachment(biz_domain=None)
        assert can_access_attachment(user, att) is True

    def test_biz_domain_product(self):
        """biz_domain='product' -> True."""
        user = _make_user()
        att = _make_attachment(biz_domain="product")
        assert can_access_attachment(user, att) is True

    def test_biz_domain_content_with_permission(self):
        """biz_domain='content' + user has content:view -> True."""
        user = _make_user(permissions=["content:view"])
        att = _make_attachment(biz_domain="content")
        assert can_access_attachment(user, att) is True

    def test_biz_domain_content_without_permission(self):
        """biz_domain='content' + user lacks content:view -> False."""
        user = _make_user(permissions=[])
        att = _make_attachment(biz_domain="content")
        assert can_access_attachment(user, att) is False

    def test_biz_domain_customer_with_permission_and_in_scope(self):
        """biz_domain='customer' + user has customer:view + in scope -> True."""
        customer_id = uuid4()
        user = _make_user(
            permissions=["customer:view"],
            visible_customer_ids={customer_id},
        )
        att = _make_attachment(biz_domain="customer", biz_scope_id=customer_id)
        assert can_access_attachment(user, att) is True

    def test_biz_domain_customer_without_permission(self):
        """biz_domain='customer' + user lacks customer:view -> False."""
        customer_id = uuid4()
        user = _make_user(
            permissions=[],
            visible_customer_ids={customer_id},
        )
        att = _make_attachment(biz_domain="customer", biz_scope_id=customer_id)
        assert can_access_attachment(user, att) is False

    def test_biz_domain_customer_not_in_scope(self):
        """biz_domain='customer' + user has permission but not in scope -> False."""
        customer_id = uuid4()
        other_customer_id = uuid4()
        user = _make_user(
            permissions=["customer:view"],
            visible_customer_ids={other_customer_id},
        )
        att = _make_attachment(biz_domain="customer", biz_scope_id=customer_id)
        assert can_access_attachment(user, att) is False

    def test_biz_domain_project_with_permission_and_in_scope(self):
        """biz_domain='project' + user has project:view + in scope -> True."""
        project_id = uuid4()
        user = _make_user(
            permissions=["project:view"],
            visible_project_ids={project_id},
        )
        att = _make_attachment(biz_domain="project", biz_scope_id=project_id)
        assert can_access_attachment(user, att) is True

    def test_biz_domain_project_without_permission(self):
        """biz_domain='project' + user lacks project:view -> False."""
        project_id = uuid4()
        user = _make_user(
            permissions=[],
            visible_project_ids={project_id},
        )
        att = _make_attachment(biz_domain="project", biz_scope_id=project_id)
        assert can_access_attachment(user, att) is False

    def test_biz_domain_project_not_in_scope(self):
        """biz_domain='project' + user has permission but not in scope -> False."""
        project_id = uuid4()
        other_project_id = uuid4()
        user = _make_user(
            permissions=["project:view"],
            visible_project_ids={other_project_id},
        )
        att = _make_attachment(biz_domain="project", biz_scope_id=project_id)
        assert can_access_attachment(user, att) is False

    def test_unknown_biz_domain(self):
        """Unknown biz_domain -> False."""
        user = _make_user(permissions=["content:view", "customer:view", "project:view"])
        att = _make_attachment(biz_domain="unknown_domain")
        assert can_access_attachment(user, att) is False

    def test_admin_bypass(self):
        """admin role bypasses all checks."""
        user = _make_user(role_code="admin", permissions=[])
        att = _make_attachment(biz_domain="customer", biz_scope_id=uuid4())
        assert can_access_attachment(user, att) is True

    def test_manager_bypass_with_permissions(self):
        """manager with appropriate permissions -> True."""
        project_id = uuid4()
        user = _make_user(
            role_code="manager",
            permissions=["project:view"],
            visible_project_ids={project_id},
        )
        att = _make_attachment(biz_domain="project", biz_scope_id=project_id)
        assert can_access_attachment(user, att) is True

    def test_manager_content_with_permission(self):
        """manager with content:view -> True."""
        user = _make_user(role_code="manager", permissions=["content:view"])
        att = _make_attachment(biz_domain="content")
        assert can_access_attachment(user, att) is True

    def test_fail_closed_no_visible_ids(self):
        """Non-admin/manager without visible_*_ids set -> fail closed."""
        user = _make_user(permissions=["customer:view", "project:view"])
        # visible_customer_ids=None, visible_project_ids=None
        att = _make_attachment(biz_domain="customer", biz_scope_id=uuid4())
        assert can_access_attachment(user, att) is False

    def test_dict_user_compatibility(self):
        """Dict-style user (JWT payload) also works."""
        user = {"role_code": "operator", "permissions": ["content:view"]}
        att = {"biz_domain": "content", "biz_scope_id": None}
        assert can_access_attachment(user, att) is True

    def test_manager_bypass_scope_check(self):
        """manager bypasses scope check but still needs permission."""
        project_id = uuid4()
        # manager has project:view but visible_project_ids=None (no scope loaded)
        user = _make_user(
            role_code="manager",
            permissions=["project:view"],
            visible_project_ids=None,
        )
        att = _make_attachment(biz_domain="project", biz_scope_id=project_id)
        # manager bypasses scope check, so this should be True
        assert can_access_attachment(user, att) is True
