"""Unit tests for data scope module (HLD §6.4).

Tests apply_data_scope and assert_object_scope with mock/simulated queries.
Uses simple fake query objects that record .where() calls.
"""

from uuid import uuid4

import pytest

from app.core.data_scope import (
    NotFoundError,
    ScopeNotDefined,
    assert_object_scope,
    apply_data_scope,
)
from app.models.content import ContentBatch, ContentItem, ContentMetricSnapshot, ContentPublication
from app.models.customer import Customer, CustomerDialogue, FollowUp, Requirement
from app.models.project import Project, ProjectAsset, ProjectMember
from app.models.reminder import Notification, Reminder


# ---------------------------------------------------------------------------
# Fake query objects that record .where() calls
# ---------------------------------------------------------------------------


class FakeQuery:
    """A fake query that records .where() calls."""

    def __init__(self):
        self.where_calls = []

    def where(self, *conditions):
        self.where_calls.extend(conditions)
        return self


# ---------------------------------------------------------------------------
# Helper to create mock objects using actual ORM models (no DB session needed)
# ---------------------------------------------------------------------------


def _make_customer(owner_sales_id=None):
    """Create a Customer instance (no DB session required)."""
    return Customer(
        id=uuid4(),
        name="Test Customer",
        owner_sales_id=owner_sales_id,
    )


def _make_project(customer_id=None, members=None, customer=None):
    """Create a Project instance (no DB session required)."""
    proj = Project(
        id=uuid4(),
        name="Test Project",
        customer_id=customer_id,
    )
    if members is not None:
        proj.members = members
    if customer is not None:
        proj.customer = customer
    return proj


def _make_project_member(user_id):
    """Create a ProjectMember instance."""
    return ProjectMember(
        id=uuid4(),
        project_id=uuid4(),
        user_id=user_id,
        member_role="designer",
    )


def _make_follow_up(customer=None):
    """Create a FollowUp instance."""
    fu = FollowUp(
        id=uuid4(),
        customer_id=uuid4(),
        follower_id=uuid4(),
        content="Test follow-up",
    )
    if customer is not None:
        fu.customer = customer
    return fu


def _make_project_asset(project=None):
    """Create a ProjectAsset instance."""
    asset = ProjectAsset(
        id=uuid4(),
        project_id=uuid4(),
        name="Test Asset",
        attachment_id=uuid4(),
    )
    if project is not None:
        asset.project = project
    return asset


def _make_content_item():
    """Create a ContentItem instance."""
    return ContentItem(
        id=uuid4(),
        batch_id=uuid4(),
        platform="xhs",
        title="Test",
        body="Test content",
    )


class TestApplyDataScope:
    """Tests for apply_data_scope read path."""

    def test_admin_passthrough_customer(self):
        """admin + Customer -> query unchanged."""
        query = FakeQuery()
        result = apply_data_scope(query, user_id=uuid4(), role_code="admin", model=Customer)
        assert result is query
        assert len(query.where_calls) == 0

    def test_manager_passthrough_customer(self):
        """manager + Customer -> query unchanged."""
        query = FakeQuery()
        result = apply_data_scope(query, user_id=uuid4(), role_code="manager", model=Customer)
        assert result is query
        assert len(query.where_calls) == 0

    def test_sales_customer_filtered_by_owner(self):
        """sales + Customer -> filtered by owner_sales_id."""
        user_id = uuid4()
        query = FakeQuery()
        result = apply_data_scope(query, user_id=user_id, role_code="sales", model=Customer)
        assert result is query
        assert len(query.where_calls) == 1

    def test_designer_customer_empty(self):
        """designer + Customer -> sa.false() (defensive empty set)."""
        query = FakeQuery()
        result = apply_data_scope(query, user_id=uuid4(), role_code="designer", model=Customer)
        assert result is query
        assert len(query.where_calls) == 1

    def test_operator_customer_empty(self):
        """operator + Customer -> sa.false()."""
        query = FakeQuery()
        result = apply_data_scope(query, user_id=uuid4(), role_code="operator", model=Customer)
        assert result is query
        assert len(query.where_calls) == 1

    def test_sales_project_own_customers_and_member_projects(self):
        """sales + Project -> own customers' projects + member projects."""
        user_id = uuid4()
        query = FakeQuery()
        result = apply_data_scope(query, user_id=user_id, role_code="sales", model=Project)
        assert result is query
        assert len(query.where_calls) == 1
        condition_str = str(query.where_calls[0])
        assert "or" in condition_str.lower()

    def test_designer_project_member_projects_only(self):
        """designer + Project -> member projects only."""
        user_id = uuid4()
        query = FakeQuery()
        result = apply_data_scope(query, user_id=user_id, role_code="designer", model=Project)
        assert result is query
        assert len(query.where_calls) == 1

    def test_sales_followup_filtered_by_visible_customers(self):
        """sales + FollowUp -> filtered by visible customer ids."""
        user_id = uuid4()
        query = FakeQuery()
        result = apply_data_scope(query, user_id=user_id, role_code="sales", model=FollowUp)
        assert result is query
        assert len(query.where_calls) == 1

    def test_designer_followup_empty(self):
        """designer + FollowUp -> empty (no visible customers)."""
        query = FakeQuery()
        result = apply_data_scope(query, user_id=uuid4(), role_code="designer", model=FollowUp)
        assert result is query
        assert len(query.where_calls) == 1

    def test_content_item_passthrough(self):
        """ContentItem -> query unchanged (content is full scope)."""
        query = FakeQuery()
        result = apply_data_scope(query, user_id=uuid4(), role_code="operator", model=ContentItem)
        assert result is query
        assert len(query.where_calls) == 0

    def test_reminder_filtered_by_assignee(self):
        """Reminder -> filtered by assignee_id."""
        user_id = uuid4()
        query = FakeQuery()
        result = apply_data_scope(query, user_id=user_id, role_code="sales", model=Reminder)
        assert result is query
        assert len(query.where_calls) == 1

    def test_notification_filtered_by_user(self):
        """Notification -> filtered by user_id."""
        user_id = uuid4()
        query = FakeQuery()
        result = apply_data_scope(query, user_id=user_id, role_code="sales", model=Notification)
        assert result is query
        assert len(query.where_calls) == 1

    def test_undefined_model_raises(self):
        """Undefined model -> raises ScopeNotDefined."""

        class UndefinedModel:
            pass

        query = FakeQuery()
        with pytest.raises(ScopeNotDefined):
            apply_data_scope(query, user_id=uuid4(), role_code="sales", model=UndefinedModel)

    def test_operator_project_empty(self):
        """operator + Project -> sa.false()."""
        query = FakeQuery()
        result = apply_data_scope(query, user_id=uuid4(), role_code="operator", model=Project)
        assert result is query
        assert len(query.where_calls) == 1

    def test_requirement_filtered_by_visible_customers(self):
        """Requirement -> filtered by visible customer ids."""
        user_id = uuid4()
        query = FakeQuery()
        result = apply_data_scope(query, user_id=user_id, role_code="sales", model=Requirement)
        assert result is query
        assert len(query.where_calls) == 1

    def test_project_asset_filtered_by_visible_projects(self):
        """ProjectAsset -> filtered by visible project ids."""
        user_id = uuid4()
        query = FakeQuery()
        result = apply_data_scope(query, user_id=user_id, role_code="designer", model=ProjectAsset)
        assert result is query
        assert len(query.where_calls) == 1

    def test_customer_dialogue_filtered_by_visible_customers(self):
        """CustomerDialogue -> filtered by visible customer ids."""
        user_id = uuid4()
        query = FakeQuery()
        result = apply_data_scope(query, user_id=user_id, role_code="sales", model=CustomerDialogue)
        assert result is query
        assert len(query.where_calls) == 1

    def test_content_batch_passthrough(self):
        """ContentBatch -> query unchanged."""
        query = FakeQuery()
        result = apply_data_scope(query, user_id=uuid4(), role_code="operator", model=ContentBatch)
        assert result is query
        assert len(query.where_calls) == 0

    def test_content_publication_passthrough(self):
        """ContentPublication -> query unchanged."""
        query = FakeQuery()
        result = apply_data_scope(query, user_id=uuid4(), role_code="operator", model=ContentPublication)
        assert result is query
        assert len(query.where_calls) == 0

    def test_content_metric_snapshot_passthrough(self):
        """ContentMetricSnapshot -> query unchanged."""
        query = FakeQuery()
        result = apply_data_scope(query, user_id=uuid4(), role_code="operator", model=ContentMetricSnapshot)
        assert result is query
        assert len(query.where_calls) == 0

    def test_project_member_filtered_by_visible_projects(self):
        """ProjectMember -> filtered by visible project ids."""
        user_id = uuid4()
        query = FakeQuery()
        result = apply_data_scope(query, user_id=user_id, role_code="designer", model=ProjectMember)
        assert result is query
        assert len(query.where_calls) == 1


class TestAssertObjectScope:
    """Tests for assert_object_scope write path."""

    def test_sales_editing_own_customer(self):
        """sales editing own customer -> ok."""
        user_id = uuid4()
        customer = _make_customer(owner_sales_id=user_id)
        assert_object_scope(customer, user_id=user_id, role_code="sales", action="edit")

    def test_sales_editing_others_customer(self):
        """sales editing others' customer -> NotFoundError."""
        user_id = uuid4()
        other_user_id = uuid4()
        customer = _make_customer(owner_sales_id=other_user_id)
        with pytest.raises(NotFoundError):
            assert_object_scope(customer, user_id=user_id, role_code="sales", action="edit")

    def test_designer_editing_project_asset_in_bound_project(self):
        """designer editing project asset in bound project -> ok."""
        user_id = uuid4()
        project = _make_project(members=[_make_project_member(user_id)])
        asset = _make_project_asset(project=project)
        assert_object_scope(asset, user_id=user_id, role_code="designer", action="edit")

    def test_designer_editing_project_asset_not_member(self):
        """designer editing project asset not member -> NotFoundError."""
        user_id = uuid4()
        project = _make_project(members=[])
        asset = _make_project_asset(project=project)
        with pytest.raises(NotFoundError):
            assert_object_scope(asset, user_id=user_id, role_code="designer", action="edit")

    def test_operator_editing_content_item(self):
        """operator editing content item -> ok."""
        item = _make_content_item()
        assert_object_scope(item, user_id=uuid4(), role_code="operator", action="edit")

    def test_admin_passthrough(self):
        """admin -> always ok."""
        customer = _make_customer(owner_sales_id=uuid4())
        assert_object_scope(customer, user_id=uuid4(), role_code="admin", action="edit")

    def test_manager_passthrough(self):
        """manager -> always ok."""
        customer = _make_customer(owner_sales_id=uuid4())
        assert_object_scope(customer, user_id=uuid4(), role_code="manager", action="edit")

    def test_none_object_raises_not_found(self):
        """None object -> NotFoundError."""
        with pytest.raises(NotFoundError):
            assert_object_scope(None, user_id=uuid4(), role_code="sales", action="edit")

    def test_undefined_model_raises_not_found(self):
        """Undefined (role, model) -> NotFoundError."""

        class UndefinedModel:
            pass

        obj = UndefinedModel()
        with pytest.raises(NotFoundError):
            assert_object_scope(obj, user_id=uuid4(), role_code="sales", action="edit")

    def test_sales_editing_own_project(self):
        """sales editing project where they own the customer -> ok."""
        user_id = uuid4()
        customer = _make_customer(owner_sales_id=user_id)
        project = _make_project(customer=customer)
        assert_object_scope(project, user_id=user_id, role_code="sales", action="edit")

    def test_sales_editing_member_project(self):
        """sales editing project where they are a member -> ok."""
        user_id = uuid4()
        project = _make_project(members=[_make_project_member(user_id)])
        assert_object_scope(project, user_id=user_id, role_code="sales", action="edit")

    def test_sales_editing_non_member_project(self):
        """sales editing project where they are not owner or member -> NotFoundError."""
        user_id = uuid4()
        customer = _make_customer(owner_sales_id=uuid4())
        project = _make_project(customer=customer, members=[])
        with pytest.raises(NotFoundError):
            assert_object_scope(project, user_id=user_id, role_code="sales", action="edit")

    def test_followup_by_customer_owner(self):
        """sales editing follow-up on own customer -> ok."""
        user_id = uuid4()
        customer = _make_customer(owner_sales_id=user_id)
        follow_up = _make_follow_up(customer=customer)
        assert_object_scope(follow_up, user_id=user_id, role_code="sales", action="edit")

    def test_followup_by_designer_on_bound_project(self):
        """designer editing follow-up on project they're member of -> ok."""
        user_id = uuid4()
        project = _make_project(members=[_make_project_member(user_id)])
        customer = _make_customer(owner_sales_id=uuid4())
        customer.projects = [project]
        follow_up = _make_follow_up(customer=customer)
        assert_object_scope(follow_up, user_id=user_id, role_code="designer", action="edit")

    def test_sales_editing_project_asset_own_project(self):
        """sales editing project asset on own project -> ok."""
        user_id = uuid4()
        customer = _make_customer(owner_sales_id=user_id)
        project = _make_project(customer=customer)
        asset = _make_project_asset(project=project)
        assert_object_scope(asset, user_id=user_id, role_code="sales", action="edit")

    def test_not_found_error_has_code(self):
        """NotFoundError has code=40401."""
        with pytest.raises(NotFoundError) as exc_info:
            assert_object_scope(None, user_id=uuid4(), role_code="sales", action="edit")
        assert exc_info.value.code == 40401
