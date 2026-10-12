"""数据范围（读 apply_data_scope / 写 assert_object_scope）— HLD §6.4。

叶子模块：只 import sqlalchemy + models（不 import app.core.config / database，
避免循环依赖；满足 tests/unit 硬约定「单元测试不依赖 DB」）。

读路径规则：
- admin/manager：全量放行。
- Customer：sales 仅本人负责的客户；其余角色防御性空集。
- Project：sales = 本人客户的项目 ∪ 绑定项目；designer = 绑定项目；其余空集。
- CustomerDialogue/Requirement/FollowUp：customer_id ∈ 可见客户集。
- ProjectAsset/ProjectMember：project_id ∈ 可见项目集。
- Content*：全量（权限码已限 operator/manager/admin）。
- Reminder/Notification：仅本人（assignee_id / user_id）。
- 未定义 model → ScopeNotDefined（禁止默认放行）。

写路径规则（P0-3）：
- 越权与不存在统一 NotFoundError（404 {code:40401}，不暴露存在性）。
- 规则表 WRITE_SCOPE 为纯数据，可单测；子资源嵌套路由的父对象范围校验是
  路径的一部分，谓词只读对象自身/预加载关系（o.customer / o.project /
  o.members），由调用方负责 eager-load。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import or_, select

from app.models.content import (
    ContentBatch,
    ContentItem,
    ContentMetricSnapshot,
    ContentPublication,
)
from app.models.customer import Customer, CustomerDialogue, FollowUp, Requirement
from app.models.project import Project, ProjectAsset, ProjectMember
from app.models.reminder import Notification, Reminder

__all__ = [
    "NotFoundError",
    "ScopeNotDefined",
    "WRITE_SCOPE",
    "apply_data_scope",
    "assert_object_scope",
]

# admin/manager 数据范围全量（§6.4）
_FULL_SCOPE_ROLES = frozenset({"admin", "manager"})


class ScopeNotDefined(Exception):
    """apply_data_scope 遇到未覆盖的模型时抛出（HLD §6.4：禁止默认放行）。"""


class NotFoundError(Exception):
    """写路径越权或对象不存在 → 统一 404（code=40401，不暴露存在性）。"""

    def __init__(self, msg: str = "资源不存在或无权访问"):
        super().__init__(msg)
        self.code = 40401
        self.msg = msg


# ---------------------------------------------------------------------------
# 读路径
# ---------------------------------------------------------------------------


def _visible_customer_ids(user_id, role_code):
    """可见客户 id 集（select 子查询，供 .in_() 使用）。

    admin/manager=全量；sales=本人负责；其余（designer/operator）=空集。
    """
    stmt = select(Customer.id)
    if role_code in _FULL_SCOPE_ROLES:
        return stmt
    if role_code == "sales":
        return stmt.where(Customer.owner_sales_id == user_id)
    return stmt.where(sa.false())


def _member_project_ids(user_id):
    """用户作为成员绑定的项目 id 子查询（designer 数据范围必需）。"""
    return select(ProjectMember.project_id).where(
        ProjectMember.user_id == user_id,
        ProjectMember.is_deleted.is_(False),
    )


def _visible_project_ids(user_id, role_code):
    """可见项目 id 集（select 子查询，供 .in_() 使用）。

    admin/manager=全量；sales=本人客户的项目 ∪ 绑定项目；designer=绑定项目；
    其余=空集。
    """
    stmt = select(Project.id)
    if role_code in _FULL_SCOPE_ROLES:
        return stmt
    if role_code == "sales":
        own_customer = select(Customer.id).where(
            Customer.owner_sales_id == user_id,
            Customer.is_deleted.is_(False),
        )
        return stmt.where(
            or_(
                Project.customer_id.in_(own_customer),
                Project.id.in_(_member_project_ids(user_id)),
            )
        )
    if role_code == "designer":
        return stmt.where(Project.id.in_(_member_project_ids(user_id)))
    return stmt.where(sa.false())


def apply_data_scope(query, *, user_id, role_code, model):
    """对查询施加行级数据范围（读路径，§6.4）。

    Args:
        query: 待过滤的 SQLAlchemy Query（调用方已自行处理 is_deleted）。
        user_id: 当前用户 id。
        role_code: 当前角色码（admin/manager/sales/designer/operator/...）。
        model: 查询对应的 ORM 模型类。

    Returns:
        追加了范围条件的 query（admin/manager 及 Content* 系原样返回）。

    Raises:
        ScopeNotDefined: model 未在规则表中定义 —— 禁止默认放行。
    """
    if role_code in _FULL_SCOPE_ROLES:
        return query
    if model is Customer:
        if role_code == "sales":
            return query.where(Customer.owner_sales_id == user_id)
        return query.where(sa.false())
    if model is Project:
        if role_code == "sales":
            return query.where(
                or_(
                    Project.customer_id.in_(_visible_customer_ids(user_id, role_code)),
                    Project.id.in_(_member_project_ids(user_id)),
                )
            )
        if role_code == "designer":
            return query.where(Project.id.in_(_member_project_ids(user_id)))
        return query.where(sa.false())
    if model in (CustomerDialogue, Requirement, FollowUp):
        return query.where(model.customer_id.in_(_visible_customer_ids(user_id, role_code)))
    if model in (ProjectAsset, ProjectMember):
        return query.where(model.project_id.in_(_visible_project_ids(user_id, role_code)))
    if model in (ContentBatch, ContentItem, ContentPublication, ContentMetricSnapshot):
        return query
    if model is Reminder:
        return query.where(model.assignee_id == user_id)
    if model is Notification:
        return query.where(model.user_id == user_id)
    raise ScopeNotDefined(model)


# ---------------------------------------------------------------------------
# 写路径（P0-3）
# ---------------------------------------------------------------------------


def _is_project_member(project, user_id) -> bool:
    """user_id 是否为 project 的成员（project.members 由调用方预加载）。"""
    if project is None:
        return False
    members = getattr(project, "members", None) or ()
    return any(getattr(m, "user_id", None) == user_id for m in members)


def _can_edit_project(project, user_id) -> bool:
    """项目可编辑判定：所属客户负责人（经 customer）或项目成员。"""
    if project is None:
        return False
    customer = getattr(project, "customer", None)
    if customer is not None and getattr(customer, "owner_sales_id", None) == user_id:
        return True
    return _is_project_member(project, user_id)


def _can_view_customer(customer, user_id) -> bool:
    """客户可查看判定：负责人，或绑定该客户任一项目的设计师（经 customer.projects）。"""
    if customer is None:
        return False
    if getattr(customer, "owner_sales_id", None) == user_id:
        return True
    projects = getattr(customer, "projects", None) or ()
    return any(_is_project_member(p, user_id) for p in projects)


# 写范围规则表（纯数据，可单测）。键为 (角色, 模型)；角色支持 "sales|designer"
# 复合键（两角色共享同一谓词）。谓词签名：(obj, user_id) -> bool。
WRITE_SCOPE = {
    ("sales", Customer): lambda o, uid: o.owner_sales_id == uid,
    ("sales", Project): lambda o, uid: _can_edit_project(o, uid),
    ("sales", ProjectAsset): lambda o, uid: _can_edit_project(o.project, uid),
    ("designer", ProjectAsset): lambda o, uid: _is_project_member(o.project, uid),
    ("sales|designer", FollowUp): lambda o, uid: _can_view_customer(o.customer, uid),
    ("operator", ContentItem): lambda o, uid: True,
}


def _write_scope_predicate(role_code, model):
    """按 (role_code, model) 查写范围谓词；未定义返回 None（禁止默认放行）。"""
    predicate = WRITE_SCOPE.get((role_code, model))
    if predicate is not None:
        return predicate
    for (roles, m), pred in WRITE_SCOPE.items():
        if isinstance(roles, str) and "|" in roles and m is model:
            if role_code in roles.split("|"):
                return pred
    return None


def assert_object_scope(obj, *, user_id, role_code, action):
    """写路径数据范围校验（§6.4 P0-3）。

    在所有 PUT/DELETE/POST 子资源取到对象后、改动前调用。

    - admin/manager：全量放行。
    - 对象不存在（None）、(role, model) 未定义写规则、或谓词判定越权：
      统一 raise NotFoundError（404 {code:40401}，不暴露存在性）。

    Args:
        obj: 待校验的 ORM 对象（谓词所需关系由调用方预加载）。
        user_id: 当前用户 id。
        role_code: 当前角色码。
        action: 审计动作名（预留上下文；规则表为纯数据，不依赖该值）。
    """
    if role_code in _FULL_SCOPE_ROLES:
        return
    if obj is None:
        raise NotFoundError()
    predicate = _write_scope_predicate(role_code, type(obj))
    if predicate is None or not predicate(obj, user_id):
        raise NotFoundError()
